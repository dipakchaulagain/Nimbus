from apscheduler.triggers.interval import IntervalTrigger
from flask import current_app
from ..utils.vcenter_sync import fetch_vms_from_vcenter, upsert_vm_records
from ..models.vcenter import VCenterConfig


def sync_vcenter_job():
    from flask import current_app
    from sqlalchemy import text
    from .. import db

    # Prevent concurrent syncs across threads/processes using a DB advisory lock
    LOCK_KEY = 872345  # arbitrary constant for vcenter sync
    try:
        acquired = db.session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
    except Exception as e:
        current_app.logger.error(f"Failed to try advisory lock: {e}")
        return

    if not acquired:
        current_app.logger.info("vCenter sync skipped: another sync is in progress")
        return

    try:
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
                # Reset session so future iterations/requests are not poisoned
                try:
                    db.session.rollback()
                except Exception:
                    pass
                current_app.logger.error(f"Sync failed for {cfg.name}: {e}")
                continue
    finally:
        try:
            db.session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            db.session.commit()
        except Exception:
            # In case of transaction state errors, make best effort to rollback
            try:
                db.session.rollback()
            except Exception:
                pass


def schedule_vcenter_sync(scheduler, app):
    interval_minutes = app.config.get('VCENTER_SYNC_INTERVAL', 30)

    def job_wrapper():
        # Ensure app context and session cleanup for background threads
        from .. import db
        with app.app_context():
            try:
                sync_vcenter_job()
            finally:
                db.session.remove()  # return connections to the pool

    scheduler.add_job(
        func=job_wrapper,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id='vcenter_sync',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

