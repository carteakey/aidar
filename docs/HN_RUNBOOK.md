# HN Scanning Runbook

Daily runbook for scanning trending Hacker News domains and syncing results to Heroku/R2.

## First-Time Setup

```bash
cp .env.example .env
# edit .env and fill LITESTREAM_* values
```

## Workers You Need

1. `Heroku web dyno` (already running):
   - Starts via [`Procfile`](../Procfile) -> `bash scripts/start.sh`
   - Serves API/UI and replicates DB while app is live.
2. `Local scanner worker` (you run manually or via cron):
   - `aidar worker ...`
   - Discovers/scans domains and writes into local `aidar.db`.

You do **not** need a second Heroku worker process for scanning unless you explicitly want one.

## One-Command Daily Job

Run:

```bash
bash scripts/hn-daily-sync.sh
```

This does:
1. Pull latest DB from R2 (`scripts/pull-from-r2.sh`)
2. Run one HN worker cycle (`--max-cycles 1`)
3. Checkpoint WAL
4. Push updated DB back to R2 (`scripts/push-to-r2.sh`)

Optional Heroku restart at the end:

```bash
RESTART_HEROKU=1 HEROKU_APP=aidar bash scripts/hn-daily-sync.sh
```

## Tunables

All can be set as env vars before running `scripts/hn-daily-sync.sh`:

- `HN_DOMAINS` (default `25`)
- `HN_STORY_LIMIT` (default `250`)
- `HN_MIN_STORY_COUNT` (default `2`)
- `DOMAIN_PAGE_LIMIT` (default `200`)
- `CONCURRENCY` (default `10`)
- `MAX_CYCLES` (default `1`)

Example:

```bash
HN_DOMAINS=40 HN_STORY_LIMIT=300 DOMAIN_PAGE_LIMIT=250 bash scripts/hn-daily-sync.sh
```

## Scheduling

Daily at 2:15 AM local time (cron):

```cron
15 2 * * * cd /Users/kchauhan/repos/aidar && /bin/bash scripts/hn-daily-sync.sh >> /tmp/aidar-hn.log 2>&1
```

## Manual Pull / Push

Pull latest from R2:

```bash
bash scripts/pull-from-r2.sh
```

Push local DB to R2:

```bash
bash scripts/push-to-r2.sh
```
