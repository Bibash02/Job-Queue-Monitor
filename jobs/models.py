from django.db import models
from django.utils import timezone

# Create your models here.
class JobType(models.TextChoices):
    IMPORT = "import", "Data import"
    EMAIL = "email", "Email"
    REPORT = "report", "Report"
    SYNC = "sync", "Sync"

class JobStatus(models.TextChoices):
    PENDING = "pending", "Pending"        # waiting for a worker
    RUNNING = "running", "Running"        # a worker claimed it
    RETRYING = "retrying", "Retrying"     # failed, will run again at next_run_at
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"           # out of attempts (dead letter)
    CANCELLED = "cancelled", "Cancelled"

ACTIVE_STATUSES = (JobStatus.PENDING, JobStatus.RETRYING, JobStatus.RUNNING)
TERMINAL_STATUSES = (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)

class Job(models.Model):
    job_type = models.CharField(max_length=20, choices=JobType.choices, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING, db_index=True
    )

    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)

    error_message = models.TextField(blank=True)  # latest error, for quick scanning
    result = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    next_run_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)   # start of latest attempt
    finished_at = models.DateTimeField(null=True, blank=True)  # set on terminal state

    locked_by = models.CharField(max_length=100, blank=True)   # worker id while running

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "next_run_at"])]

    def __str__(self):
        return f"#{self.pk} {self.job_type} [{self.status}]"

    @property
    def is_terminal(self):
        return self.status in TERMINAL_STATUSES

    @property
    def can_retry(self):
        return self.status in (JobStatus.FAILED, JobStatus.CANCELLED)

    @property
    def duration(self):
        """Seconds taken by the latest attempt, or None if not finished."""
        last = self.attempt_logs.order_by("-number").first()
        return last.duration if last else None

class JobAttempt(models.Model):
    """One row per execution try. This is the developer-facing audit log."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="attempt_logs")
    number = models.PositiveIntegerField()
    worker = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(null=True)  # null while running
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]
        unique_together = [("job", "number")]

    def __str__(self):
        return f"Job #{self.job_id} attempt {self.number}"

    @property
    def duration(self):
        if self.finished_at:
            return round((self.finished_at - self.started_at).total_seconds(), 3)
        return None