from apscheduler.triggers.interval import IntervalTrigger
from flask import current_app
from ..utils.vcenter_sync import fetch_vms_from_vcenter, upsert_vm_records
from ..models.vcenter import VCenterConfig


def sync_vcenter_job():
    from flask import current_app
    configs = VCenterConfig.query.filter_by(enabled=True).all()
    
    if not configs:
        current_app.logger.info("No enabled vCenter configurations found")
        return
    
    for cfg in configs:
        try:
            current_app.logger.info(f"Starting sync for vCenter: {cfg.name}")
            vms = fetch_vms_from_vcenter(cfg)
            updated_count = upsert_vm_records(vms)
            current_app.logger.info(f"Sync completed for {cfg.name}: {updated_count} VMs updated")
        except Exception as e:
            current_app.logger.error(f"Sync failed for {cfg.name}: {e}")
            continue


def schedule_vcenter_sync(scheduler, app):
    interval_minutes = app.config.get('VCENTER_SYNC_INTERVAL', 30)
    scheduler.add_job(
        func=lambda: app.app_context().push() or sync_vcenter_job(),
        trigger=IntervalTrigger(minutes=interval_minutes),
        id='vcenter_sync',
        replace_existing=True,
    )

