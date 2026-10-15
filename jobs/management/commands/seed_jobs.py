import random

from django.core.management.base import BaseCommand

from jobs import services


class Command(BaseCommand):
    help = "Enqueue a mix of demo jobs (including some that can never succeed)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=20)

    def handle(self, *args, **opts):
        for i in range(opts["count"]):
            kind = random.choice(["import", "email", "report", "sync"])
            payload = {
                "import": {"file": f"customers_{i}.csv"},
                "email": {"to": f"user{i}@example.com", "subject": "Your invoice"},
                "report": {"name": "weekly-sales"},
                "sync": {"target": "crm"},
            }[kind]
            services.enqueue(kind, payload)
        # deliberately broken jobs so the failure path is visible
        services.enqueue("email", {"to": "not-an-email"})
        services.enqueue("import", {})
        services.enqueue("sync", {"fail_rate": 1.0}, max_attempts=3)
        self.stdout.write(self.style.SUCCESS(f"enqueued {opts['count'] + 3} jobs"))
