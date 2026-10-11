"""
Simulated job handlers. Each takes the job payload and returns a JSON-able result,
or raises. Swap the bodies for real work (CSV import, SMTP send, ...) later.

Raise PermanentJobError for failures that retrying cannot fix (bad input);
any other exception is treated as transient and retried with backoff.
"""
import random
import time


class PermanentJobError(Exception):
    """Do not retry: the job can never succeed as-is."""


def _maybe_fail(payload, default_rate):
    # payload["fail_rate"] lets tests/demos force behaviour deterministically
    rate = payload.get("fail_rate", default_rate)
    if random.random() < rate:
        raise ConnectionError("simulated transient failure (upstream unavailable)")


def handle_import(payload):
    if not payload.get("file"):
        raise PermanentJobError("payload.file is required")
    time.sleep(payload.get("sleep", 0.3))
    _maybe_fail(payload, 0.3)
    return {"rows_imported": random.randint(100, 5000), "file": payload["file"]}


def handle_email(payload):
    if "@" not in str(payload.get("to", "")):
        raise PermanentJobError(f"invalid recipient: {payload.get('to')!r}")
    time.sleep(payload.get("sleep", 0.1))
    _maybe_fail(payload, 0.25)
    return {"sent_to": payload["to"], "subject": payload.get("subject", "")}


def handle_report(payload):
    time.sleep(payload.get("sleep", 0.5))
    _maybe_fail(payload, 0.2)
    return {"report": payload.get("name", "weekly"), "pages": random.randint(2, 40)}


def handle_sync(payload):
    time.sleep(payload.get("sleep", 0.3))
    _maybe_fail(payload, 0.4)
    return {"records_synced": random.randint(10, 800), "target": payload.get("target", "crm")}


HANDLERS = {
    "import": handle_import,
    "email": handle_email,
    "report": handle_report,
    "sync": handle_sync,
}
