import ssl
import socket
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from flask import current_app

from ..models.vm import VM, VMDisks, VMNic
from ..models.vcenter import VCenterConfig


def _connect_vcenter(cfg: VCenterConfig):
    """Connect to vCenter and return a service instance.

    Tries verified SSL first (unless disabled), then falls back to an
    unverified context if needed. Sets a conservative socket timeout.
    """
    context = None
    if cfg.disable_ssl:
        context = ssl._create_unverified_context()

    # Set socket timeout globally (pyVmomi uses sockets internally)
    socket.setdefaulttimeout(30)  # 30 second timeout

    try:
        return SmartConnect(
            host=cfg.host,
            user=cfg.username,
            pwd=cfg.password,
            sslContext=context,
            port=443,  # Default vCenter port
        )
    except Exception as e:
        # If SSL fails, try with unverified context if not already attempted
        if not cfg.disable_ssl:
            try:
                context = ssl._create_unverified_context()
                return SmartConnect(
                    host=cfg.host,
                    user=cfg.username,
                    pwd=cfg.password,
                    sslContext=context,
                    port=443,
                )
            except Exception as e2:
                current_app.logger.error(f"vCenter connect failed (fallback): {e2}")
                raise
        else:
            current_app.logger.error(f"vCenter connect failed: {e}")
            raise


def _resolve_network_name(dev, content):
    if hasattr(dev.backing, "deviceName"):
        return dev.backing.deviceName
    if hasattr(dev.backing, "port"):
        portgroup_key = getattr(dev.backing.port, "portgroupKey", None)
        if portgroup_key:
            for dc in content.rootFolder.childEntity:
                if hasattr(dc, "network"):
                    for net in dc.network:
                        if hasattr(net, "key") and net.key == portgroup_key:
                            return net.name
    return None


def _normalize_decimal(num: Optional[float], places: str = "0.01") -> Optional[Decimal]:
    """Normalize float/None to Decimal with fixed precision for reliable comparisons."""
    if num is None:
        return None
    try:
        d = Decimal(str(num)).quantize(Decimal(places), rounding=ROUND_HALF_UP)
        return d
    except Exception:
        return None


def fetch_vms_from_vcenter(cfg: VCenterConfig) -> List[Dict]:
    """Fetch VM inventory from vCenter with robust per-VM error handling.

    - Ensures the container view is destroyed
    - Associates IPs to NICs by MAC address when possible
    - Logs and continues on per-VM errors
    """
    si = _connect_vcenter(cfg)
    try:
        content = si.RetrieveContent()
        vm_list: List[Dict] = []

        for datacenter in content.rootFolder.childEntity:
            if not hasattr(datacenter, "vmFolder"):
                continue

            vm_folder = datacenter.vmFolder
            vm_view = content.viewManager.CreateContainerView(
                vm_folder, [vim.VirtualMachine], True
            )
            try:
                for vm in vm_view.view:
                    try:
                        summary = vm.summary

                        # Build NIC list (hardware-defined)
                        nics = []
                        if vm.config and vm.config.hardware:
                            for dev in vm.config.hardware.device:
                                if isinstance(dev, vim.vm.device.VirtualEthernetCard):
                                    network_name = _resolve_network_name(dev, content)
                                    nics.append({
                                        "label": getattr(dev.deviceInfo, "label", None),
                                        "mac": getattr(dev, "macAddress", None),
                                        "network": network_name,
                                        "connected": getattr(getattr(dev, "connectable", None), "connected", False),
                                        "nic_type": type(dev).__name__,
                                    })

                        # Build MAC -> IP addresses map from guest info
                        mac_to_ips = {}
                        if vm.guest and vm.guest.net:
                            for net in vm.guest.net:
                                mac = getattr(net, "macAddress", None)
                                ips = list(getattr(net, "ipAddress", []) or [])
                                if mac:
                                    mac_to_ips[mac] = ips

                        # Attach IPs to NIC entries by MAC (fallback: index order)
                        for idx, nic in enumerate(nics):
                            mac = nic.get("mac")
                            if mac and mac in mac_to_ips:
                                nic["ip_addresses"] = mac_to_ips[mac]
                            else:
                                # Fallback to index-based guest.net if available
                                if vm.guest and vm.guest.net and idx < len(vm.guest.net):
                                    nic["ip_addresses"] = list(getattr(vm.guest.net[idx], "ipAddress", []) or [])

                        # Disks
                        disks = []
                        if vm.config and vm.config.hardware:
                            for dev in vm.config.hardware.device:
                                if isinstance(dev, vim.vm.device.VirtualDisk):
                                    size_gb = round(dev.capacityInKB / (1024 ** 2), 2)
                                    disks.append({
                                        "label": getattr(dev.deviceInfo, "label", None),
                                        "size_gb": size_gb,
                                    })

                        host_name = None
                        if summary.runtime.host:
                            try:
                                host_name = summary.runtime.host.name
                            except Exception:
                                host_name = str(summary.runtime.host)

                        vm_info = {
                            "vm_id": getattr(summary.config, "instanceUuid", None),
                            "name": getattr(summary.config, "name", None),
                            "cpu": getattr(summary.config, "numCpu", None),
                            "memoryMB": getattr(summary.config, "memorySizeMB", None),
                            "assigned_disks": disks,
                            "power_state": getattr(summary.runtime, "powerState", None),
                            "guestOS": getattr(summary.config, "guestFullName", None),
                            "nics": nics,
                            "created_date": getattr(summary.config, "createDate", None),
                            "last_booted_date": getattr(summary.runtime, "bootTime", None),
                            "hypervisor": host_name,
                        }

                        vm_list.append(vm_info)
                    except Exception as vm_err:
                        current_app.logger.error(f"Failed to process VM in {getattr(datacenter, 'name', 'Unknown DC')}: {vm_err}")
                        continue
            finally:
                vm_view.Destroy()

        return vm_list
    finally:
        try:
            Disconnect(si)
        except Exception:
            pass


def upsert_vm_records(vms: List[Dict]) -> int:
    """Upsert VM records with proper validation and type normalization.

    Key fixes:
    - Initialize all fields (including disks/NICs) for new VMs
    - Normalize disk sizes to Decimal for stable comparisons
    - Avoid storing string "None" for power_state
    - Log and skip invalid entries cleanly
    """
    from .. import db

    updated = 0
    changed = 0
    skipped = 0

    # Deduplicate payload by vm_id to avoid double INSERTs within one transaction
    seen_ids = set()

    for data in vms:
        vm_id = data.get("vm_id")
        vm_name = data.get("name")

        if vm_id:
            if vm_id in seen_ids:
                current_app.logger.debug(f"Duplicate VM in payload skipped: {vm_name} ({vm_id})")
                continue
            seen_ids.add(vm_id)

        # Basic validation
        if not vm_id and not vm_name:
            current_app.logger.warning("Skipping VM with missing vm_id and name")
            skipped += 1
            continue

        # Try resolve by name if id missing
        if not vm_id and vm_name:
            with db.session.no_autoflush:
                existing_by_name = VM.query.filter_by(name=vm_name).first()
            if existing_by_name:
                current_app.logger.info(
                    f"Found existing VM with name '{vm_name}', using id '{existing_by_name.id}'"
                )
                vm_id = existing_by_name.id
            else:
                current_app.logger.warning(f"Skipping VM '{vm_name}' due to missing vm_id")
                skipped += 1
                continue

        # Load or create VM using SELECT FOR UPDATE to avoid race-conditions
        with db.session.no_autoflush:
            vm: Optional[VM] = VM.query.with_for_update(of=VM).get(vm_id)

        is_new = vm is None
        if is_new:
            # Double-check not created by another transaction after the SELECT
            with db.session.no_autoflush:
                vm = VM.query.get(vm_id)
            if vm is None:
                vm = VM(id=vm_id, name=vm_name or vm_id)
                db.session.add(vm)

        fields_changed = False

        # Update basic fields for both new and existing VMs
        if vm.name != data.get("name"):
            vm.name = data.get("name")
            fields_changed = True

        if vm.cpu != data.get("cpu"):
            vm.cpu = data.get("cpu")
            fields_changed = True

        memory_mb = data.get("memoryMB")
        if vm.memory_mb != memory_mb:
            vm.memory_mb = memory_mb
            fields_changed = True

        if vm.guest_os != data.get("guestOS"):
            vm.guest_os = data.get("guestOS")
            fields_changed = True

        ps_raw = data.get("power_state")
        ps_val = str(ps_raw) if ps_raw is not None else None
        if vm.power_state != ps_val:
            vm.power_state = ps_val
            fields_changed = True

        if vm.hypervisor != data.get("hypervisor"):
            vm.hypervisor = data.get("hypervisor")
            fields_changed = True

        # Dates
        cd = data.get("created_date")
        bd = data.get("last_booted_date")
        created_date = cd if isinstance(cd, datetime) else None
        last_booted_date = bd if isinstance(bd, datetime) else None

        if vm.created_date != created_date:
            vm.created_date = created_date
            fields_changed = True

        if vm.last_booted_date != last_booted_date:
            vm.last_booted_date = last_booted_date
            fields_changed = True

        # Disks: normalize to Decimal for stable comparisons
        current_disks = {(d.label, _normalize_decimal(float(d.size_gb))) for d in vm.disks}
        new_disks = {
            (
                d.get("label"),
                _normalize_decimal(d.get("size_gb")),
            )
            for d in data.get("assigned_disks", [])
        }

        if current_disks != new_disks:
            vm.disks.clear()
            for d in data.get("assigned_disks", []):
                vm.disks.append(
                    VMDisks(
                        label=d.get("label"),
                        size_gb=_normalize_decimal(d.get("size_gb")),
                    )
                )
            fields_changed = True

        # NICs
        current_nics = {
            (
                n.label,
                n.mac,
                n.network,
                bool(n.connected),
                n.nic_type,
                tuple(n.ip_addresses) if n.ip_addresses else (),
            )
            for n in vm.nics
        }
        new_nics = {
            (
                n.get("label"),
                n.get("mac"),
                n.get("network"),
                bool(n.get("connected")),
                n.get("nic_type"),
                tuple(n.get("ip_addresses", []) or ()),
            )
            for n in data.get("nics", [])
        }

        if current_nics != new_nics:
            vm.nics.clear()
            for n in data.get("nics", []):
                vm.nics.append(
                    VMNic(
                        label=n.get("label"),
                        mac=n.get("mac"),
                        network=n.get("network"),
                        connected=bool(n.get("connected")),
                        nic_type=n.get("nic_type"),
                        ip_addresses=n.get("ip_addresses"),
                    )
                )
            fields_changed = True

        if is_new or fields_changed:
            changed += 1
            updated += 1
            lvl = current_app.logger.info if is_new else current_app.logger.debug
            lvl(f"{'Created' if is_new else 'Updated'} VM: {vm.name} ({vm_id})")

    # Commit all changes at once for efficiency and handle failures cleanly
    from .. import db as _db
    try:
        _db.session.commit()
    except Exception as commit_err:
        current_app.logger.error(f"Commit failed during VM upsert: {commit_err}")
        try:
            _db.session.rollback()
        except Exception:
            pass
        raise

    current_app.logger.info(
        f"Sync completed: {updated} VMs processed, {changed} created/changed, {skipped} skipped"
    )
    return updated