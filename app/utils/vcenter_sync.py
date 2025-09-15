import ssl
import socket
from datetime import datetime
from typing import List, Dict

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from flask import current_app

from ..models.vm import VM, VMDisks, VMNic
from ..models.vcenter import VCenterConfig


def _connect_vcenter(cfg: VCenterConfig):
    context = None
    if cfg.disable_ssl:
        context = ssl._create_unverified_context()
    
    # Set socket timeout
    socket.setdefaulttimeout(30)  # 30 second timeout
    
    try:
        si = SmartConnect(
            host=cfg.host,
            user=cfg.username,
            pwd=cfg.password,
            sslContext=context,
            port=443,  # Default vCenter port
        )
        return si
    except Exception as e:
        # If SSL fails, try with unverified context
        if not cfg.disable_ssl:
            context = ssl._create_unverified_context()
            si = SmartConnect(
                host=cfg.host,
                user=cfg.username,
                pwd=cfg.password,
                sslContext=context,
                port=443,
            )
            return si
        else:
            raise e


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


def fetch_vms_from_vcenter(cfg: VCenterConfig) -> List[Dict]:
    si = _connect_vcenter(cfg)
    content = si.RetrieveContent()
    vm_list = []

    for datacenter in content.rootFolder.childEntity:
        if hasattr(datacenter, "vmFolder"):
            vm_folder = datacenter.vmFolder
            vm_view = content.viewManager.CreateContainerView(
                vm_folder, [vim.VirtualMachine], True
            )

            for vm in vm_view.view:
                summary = vm.summary

                disks = []
                if vm.config and vm.config.hardware:
                    for dev in vm.config.hardware.device:
                        if isinstance(dev, vim.vm.device.VirtualDisk):
                            disks.append({
                                "label": dev.deviceInfo.label,
                                "size_gb": round(dev.capacityInKB / (1024**2), 2),
                            })

                nics = []
                if vm.config and vm.config.hardware:
                    for dev in vm.config.hardware.device:
                        if isinstance(dev, vim.vm.device.VirtualEthernetCard):
                            network_name = _resolve_network_name(dev, content)
                            nic_info = {
                                "label": dev.deviceInfo.label,
                                "mac": dev.macAddress,
                                "network": network_name,
                                "connected": dev.connectable.connected,
                                "nic_type": type(dev).__name__,
                            }
                            nics.append(nic_info)

                if vm.guest and vm.guest.net:
                    for idx, net in enumerate(vm.guest.net):
                        if idx < len(nics):
                            nics[idx]["ip_addresses"] = net.ipAddress

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

            vm_view.Destroy()

    Disconnect(si)
    return vm_list


def upsert_vm_records(vms: List[Dict]) -> int:
    from .. import db
    updated = 0
    for data in vms:
        vm_id = data.get("vm_id")
        vm_name = data.get("name")

        # Handle missing vm_id
        if not vm_id:
            if not vm_name:
                current_app.logger.warning("Skipping VM with missing vm_id and name")
                continue
            # Check if a VM with the same name exists
            with db.session.no_autoflush:
                vm = VM.query.filter_by(name=vm_name).first()
            if vm:
                current_app.logger.info(f"Found existing VM with name '{vm_name}', using id '{vm.id}'")
                vm_id = vm.id
            else:
                # Generate a new UUID if no existing VM is found
                vm_id = str(uuid.uuid4())
                current_app.logger.warning(f"Generated new vm_id '{vm_id}' for VM '{vm_name}' with missing instanceUuid")

        # Query for existing VM or create new one
        with db.session.no_autoflush:
            vm = VM.query.get(vm_id) or VM(id=vm_id, name=vm_name)

        vm.name = data.get("name")
        vm.cpu = data.get("cpu")
        vm.memory_mb = data.get("memoryMB")
        vm.guest_os = data.get("guestOS")
        vm.power_state = str(data.get("power_state"))
        vm.hypervisor = data.get("hypervisor")
        cd = data.get("created_date")
        bd = data.get("last_booted_date")
        vm.created_date = cd if isinstance(cd, datetime) else None
        vm.last_booted_date = bd if isinstance(bd, datetime) else None

        # Replace children
        vm.disks.clear()
        for d in data.get("assigned_disks", []):
            vm.disks.append(VMDisks(label=d.get("label"), size_gb=d.get("size_gb")))

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

        db.session.add(vm)
        updated += 1

    db.session.commit()
    return updated

