import os
import socket
import time

from django.core.management.base import BaseCommand

from jobs import services


class Command(BaseCommand):
    help = "Simulated worker: polls for due jobs and runs them. Ctrl+C to stop."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Drain due jobs, then exit")
        parser.add_argument("--sleep", type=float, default=1.0, help="Idle poll interval (s)")

    def handle(self, *args, **opts):
        worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.stdout.write(f"worker {worker_id} started")
        try:
            while True:
                recovered = services.recover_stale_jobs()
                if recovered:
                    self.stdout.write(self.style.WARNING(f"recovered {recovered} stale job(s)"))
                job = services.claim_next(worker_id)
                if job is None:
                    if opts["once"]:
                        break
                    time.sleep(opts["sleep"])
                    continue
                self.stdout.write(f"-> #{job.pk} {job.job_type} attempt {job.attempts}/{job.max_attempts}")
                job = services.execute(job)
                line = f"   #{job.pk} {job.status}"
                if job.error_message:
                    line += f" ({job.error_message})"
                style = self.style.SUCCESS if job.status == "succeeded" else self.style.ERROR
                self.stdout.write(style(line))
        except KeyboardInterrupt:
            self.stdout.write("worker stopped")
