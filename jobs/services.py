"""
Job lifecycle logic. Views, admin and the worker all go through here so the
state machine lives in exactly one place.

    pending ──claim──> running ──ok──────────> succeeded
                         │
                         ├─ error, attempts < max ─> retrying ──(next_run_at)──> running
                         └─ error, out of attempts / permanent ─> failed
    failed / cancelled ──manual retry──> pending
    pending / retrying ──cancel──> cancelled
"""
import traceback as tb_module
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .handlers import HANDLERS, PermanentJobError
from .models import Job, JobAttempt, JobStatus


def enqueue(job_type, payload=None, max_attempts=None, delay_seconds=0):
    return Job.objects.create(
        job_type=job_type,
        payload=payload or {},
        max_attempts=max_attempts or settings.JOB_DEFAULT_MAX_ATTEMPTS,
        next_run_at=timezone.now() + timedelta(seconds=delay_seconds),
    )


def backoff_seconds(attempt_number):
    """Exponential backoff: 5s, 10s, 20s, ... capped."""
    delay = settings.JOB_BACKOFF_BASE_SECONDS * (2 ** (attempt_number - 1))
    return min(delay, settings.JOB_BACKOFF_MAX_SECONDS)


def recover_stale_jobs():
    """A worker that died mid-job leaves it 'running' forever. Fail that attempt."""
    cutoff = timezone.now() - timedelta(seconds=settings.JOB_STALE_RUNNING_SECONDS)
    recovered = 0
    for job in Job.objects.filter(status=JobStatus.RUNNING, started_at__lt=cutoff):
        _record_failure(job, "worker lost: job exceeded stale timeout", "", permanent=False)
        recovered += 1
    return recovered


def claim_next(worker_id):
    """Atomically take the oldest due job. Safe with several workers on Postgres
    (SKIP LOCKED); on SQLite writes are serialized so it is still correct."""
    now = timezone.now()
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status__in=[JobStatus.PENDING, JobStatus.RETRYING], next_run_at__lte=now)
            .order_by("next_run_at", "id")
            .first()
        )
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = now
        job.finished_at = None
        job.locked_by = worker_id
        job.save(update_fields=["status", "attempts", "started_at", "finished_at", "locked_by"])
        JobAttempt.objects.create(job=job, number=job.attempts, worker=worker_id, started_at=now)
        return job


def _close_attempt(job, success, error="", trace=""):
    JobAttempt.objects.filter(job=job, number=job.attempts).update(
        finished_at=timezone.now(), success=success, error_message=error, traceback=trace
    )


def _record_success(job, result):
    _close_attempt(job, True)
    job.status = JobStatus.SUCCEEDED
    job.result = result
    job.error_message = ""
    job.finished_at = timezone.now()
    job.locked_by = ""
    job.save(update_fields=["status", "result", "error_message", "finished_at", "locked_by"])


def _record_failure(job, error, trace, permanent):
    _close_attempt(job, False, error, trace)
    job.error_message = error
    job.locked_by = ""
    if permanent or job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.finished_at = timezone.now()
    else:
        job.status = JobStatus.RETRYING
        job.next_run_at = timezone.now() + timedelta(seconds=backoff_seconds(job.attempts))
        job.finished_at = None
    job.save(update_fields=["status", "error_message", "next_run_at", "finished_at", "locked_by"])


def execute(job):
    """Run the handler for a claimed job and record the outcome."""
    handler = HANDLERS.get(job.job_type)
    if handler is None:
        _record_failure(job, f"no handler for job type {job.job_type!r}", "", permanent=True)
        return job
    try:
        result = handler(job.payload)
    except PermanentJobError as exc:
        _record_failure(job, str(exc), tb_module.format_exc(), permanent=True)
    except Exception as exc:  # noqa: BLE001 - worker must survive any handler bug
        _record_failure(job, f"{type(exc).__name__}: {exc}", tb_module.format_exc(), permanent=False)
    else:
        _record_success(job, result)
    job.refresh_from_db()
    return job


def retry_now(job):
    """Manual retry for failed/cancelled jobs. Gives it a fresh attempt budget."""
    if not job.can_retry:
        raise ValueError(f"cannot retry a job in status {job.status!r}")
    job.status = JobStatus.PENDING
    job.max_attempts = job.attempts + settings.JOB_DEFAULT_MAX_ATTEMPTS
    job.next_run_at = timezone.now()
    job.finished_at = None
    job.save(update_fields=["status", "max_attempts", "next_run_at", "finished_at"])
    return job


def cancel(job):
    if job.status not in (JobStatus.PENDING, JobStatus.RETRYING):
        raise ValueError(f"cannot cancel a job in status {job.status!r}")
    job.status = JobStatus.CANCELLED
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "finished_at"])
    return job


def stats():
    counts = dict(Job.objects.values_list("status").annotate(n=Count("id")))
    total = sum(counts.values())
    done = counts.get(JobStatus.SUCCEEDED, 0)
    failed = counts.get(JobStatus.FAILED, 0)
    finished = done + failed
    return {
        "total": total,
        "by_status": {s.value: counts.get(s.value, 0) for s in JobStatus},
        "success_rate": round(done / finished * 100, 1) if finished else None,
        "retried_jobs": Job.objects.filter(attempts__gt=1).count(),
    }
