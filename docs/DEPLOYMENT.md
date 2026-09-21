# Deployment and storage

The repository includes a minimal `Dockerfile` and `docker-compose.yml` for a
web process and an optional worker sharing one persistent SQLite volume.

```bash
cp deploy/domains.txt.example deploy/domains.txt
docker compose build
docker compose up -d web
curl http://localhost:8000/healthz
```

The web process can be run as a read-only replica with
`AIDAR_READ_ONLY=true`. In that mode `/submit` and `/admin/delete-domain` return
403 while read pages, `/api/*`, `/feed.xml`, and `/healthz` remain available.
Keep the worker as the only process with write responsibility.

## Persistent volumes

SQLite must live on a persistent Fly.io volume (or the Compose named volume),
not an ephemeral container filesystem. Keep WAL and shared-volume ownership
explicit; do not run two independent SQLite copies and merge them later.

## Backup and restore

Use SQLite's online backup API or an atomic `VACUUM INTO` snapshot while the
database is reachable, then upload the snapshot to an encrypted R2/S3 bucket.
Retain at least daily snapshots plus a short rolling window, and test restore
into a separate database before replacing production data. Credentials belong in
the deployment secret manager, never in the image, Compose file, or repository.

The backup job should record the source schema version, snapshot checksum, and
timestamp. A dry-run must verify destination permissions and checksum handling
without deleting old snapshots.
