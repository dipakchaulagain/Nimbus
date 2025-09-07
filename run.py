from app import create_app, db, scheduler

app = create_app()

# Initialize scheduler after app is created to avoid circular imports
from app.scheduler.tasks import schedule_vcenter_sync
with app.app_context():
    schedule_vcenter_sync(scheduler, app)
    if not scheduler.running:
        scheduler.start()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

