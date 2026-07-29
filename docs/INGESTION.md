# Corpus ingestion

Aidar uses one discovery, URL-filtering, fetch-validation, and scan path for batch CLI scans,
tracked domains, the background worker, and web-triggered scans.

## Policy

- Discovery tries a sitemap first and falls back to RSS/Atom in `auto` mode.
- Only HTTP(S) URLs on the submitted host are accepted for domain scans.
- Feed, tag, category, author, archive, pagination, search, and `/doc/` paths are filtered before
  fetching. Binary, document, media, data, script, style, and feed extensions are also filtered.
- Duplicate URLs are attempted once.
- Responses must declare HTML, XHTML, or plain text when a content type is present.
- Extracted text must contain at least 50 words by default. A declared non-English language is
  rejected; unknown language is retained rather than guessed.
- Redirects are followed by the HTTP client. Redirects to another host or to a filtered route are
  rejected; accepted same-host redirects retain the original discovered URL as the corpus key.

Fetches have a 30-second timeout. Aidar makes one request per scan attempt and does not
automatically retry timeouts, 403, 429, or 5xx responses. This avoids multiplying load or bypassing
publisher access controls. A later scheduled run may try a transient failure again; 403 responses
are recorded as `http_403` and are never worked around.

## Observability

Run summaries report `discovered`, `filtered`, `attempted`, `saved`, and `failed`, with counts by
reason. Web-triggered summaries are available from `/api/scan-status/{domain}`. Common reasons
include `non_prose_path`, `non_prose_extension`, `external_host`, `short_text`, `non_english`,
`http_403`, `http_429`, `http_5xx`, `timeout`, and `network_error`.

Audit an existing database without modifying it:

```bash
uv run aidar audit-corpus --db aidar.db
uv run aidar --output json audit-corpus --db aidar.db
```

The audit flags stored non-prose URL shapes and short extracts. Review flagged rows before taking
any cleanup action; the command never deletes or changes corpus data.
