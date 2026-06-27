# Foundation Local Runbook

## API health skeleton

```bash
PYTHONPATH=src python -m quantum.api.main --host 127.0.0.1 --port 8080
```

Endpoint:

```text
GET /health/technical
```

## Worker one-shot skeleton

```bash
PYTHONPATH=src python -m quantum.worker.main --once
```

## Tests

```bash
PYTHONPATH=src python -m quantum.scripts.ci
```

## Important limitation

These commands do not connect to PostgreSQL, object storage, Wildberries, GitHub,
or any production system.
