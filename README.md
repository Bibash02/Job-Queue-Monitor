# Job Queue Monitor

Django + DRF job queue with a simulated worker, retry/backoff, an admin screen and a staff dashboard.

## Run

```bash
pip install django djangorestframework
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_jobs --count 20      # demo jobs (3 are built to fail)
python manage.py run_worker                # --once to drain and exit
python manage.py runserver
```

- Dashboard: http://localhost:8000/dashboard/ (staff login, auto-refresh 5s)
- Admin: /admin/jobs/job/ (attempt history inline, Retry / Cancel actions)
- API (staff only): `GET /api/jobs/?status=failed`, `GET /api/jobs/<id>/`, `POST /api/jobs/`,
  `POST /api/jobs/<id>/retry/`, `POST /api/jobs/<id>/cancel/`, `GET /api/jobs/stats/`

## Lifecycle

```
pending -> running -> succeeded
              |-> retrying (backoff 5s,10s,20s... capped 300s) -> running
              |-> failed (out of attempts, or PermanentJobError)
failed/cancelled -> pending (manual retry, fresh attempt budget)
pending/retrying -> cancelled
```

- `Job` holds current state (status, attempts, error_message, started_at, finished_at, next_run_at).
- `JobAttempt` is one row per try with worker id, timings, error and traceback.
- `services.py` is the only place state changes happen; worker, API and admin all call it.
- `claim_next` uses `select_for_update(skip_locked=True)`, so multiple workers are safe on Postgres.
- `recover_stale_jobs` fails attempts stuck in `running` (crashed worker) so they get retried.
- Add a job type: write a function in `handlers.py` and register it in `HANDLERS`.

## Tests

`python manage.py test jobs`
