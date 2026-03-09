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

For existing domains from a file (instead of HN trending):

```bash
bash scripts/domains-daily-sync.sh
```

Defaults to `DOMAINS_FILE=domains.txt` (override with env var).

Optional Heroku restart at the end:

```bash
RESTART_HEROKU=1 HEROKU_APP=aidar bash scripts/hn-daily-sync.sh
```

## Tunables

All can be set as env vars before running `scripts/hn-daily-sync.sh`:

- `HN_DOMAINS` (default `25`) — top N domains from `/topstories`
- `HN_STORY_LIMIT` (default `250`) — how many top stories to sample
- `HN_MIN_STORY_COUNT` (default `2`) — minimum stories per domain before inclusion
- `HN_NEW_DOMAINS` (default `20`) — top N domains from `/newstories` (set to `0` to disable)
- `HN_NEW_STORY_LIMIT` (default `100`) — how many new stories to sample
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

## Domain Management

### Excluding domains from HN discovery

Edit `domain_exclude.txt` — one domain per line, `#` for comments:

```
# Paywalled, no public content
bloomberg.com
# Not prose (ecommerce, airport, etc.)
etsy.com
```

Domains in this file are skipped when HN trending/new stories are scanned.
Domains in `domains.txt` are **never** excluded — they're always scanned.

### Flushing excluded domains from DB

After editing `domain_exclude.txt`, remove their existing scans:

```bash
bash scripts/db-cleanup-excluded.sh
```

Shows per-domain scan counts, asks for confirmation, then deletes.
`pattern_scores` rows are removed automatically via `ON DELETE CASCADE`.

### Deleting a domain via the web UI

Set `AIDAR_ADMIN_KEY` in your environment (and Heroku config vars):

```bash
# .env
AIDAR_ADMIN_KEY=yourkey

# Heroku
heroku config:set AIDAR_ADMIN_KEY=yourkey --app aidar
```

An **⚙ admin** accordion appears at the bottom of each domain page.
Enter the key and confirm to wipe all scans for that domain.

## Manual Pull / Push

Pull latest from R2:

```bash
bash scripts/pull-from-r2.sh
```

Push local DB to R2:

```bash
bash scripts/push-to-r2.sh
```
