from __future__ import annotations

import click

from aidar.cli.main import aidar
from aidar.core.discovery import discover_urls, normalize_domain


@aidar.command()
@click.argument("domain")
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Write URLs to file instead of stdout",
)
@click.option(
    "--limit",
    default=0,
    show_default=True,
    help="Max URLs to return (0 = all)",
)
@click.option(
    "--type",
    "source_type",
    type=click.Choice(["auto", "sitemap", "rss"]),
    default="auto",
    show_default=True,
    help="Discovery method",
)
@click.option(
    "--filter-ext",
    default=".html,.htm,/",
    show_default=True,
    help="Comma-separated URL suffixes/patterns to keep (empty = keep all)",
)
@click.pass_context
def discover(
    ctx: click.Context,
    domain: str,
    output: str | None,
    limit: int,
    source_type: str,
    filter_ext: str,
) -> None:
    """Discover article URLs for a domain via sitemap or RSS feed.

    Outputs one URL per line to stdout (or --output file).
    Pipe directly into --batch: aidar discover example.com -o urls.txt
    """
    base_url = normalize_domain(domain)
    click.echo(f"Discovering URLs for {base_url} ...", err=True)
    urls, method = discover_urls(base_url, source_type)
    if urls:
        click.echo(f"Found {len(urls)} URLs via {method}.", err=True)

    if not urls:
        click.echo(
            f"No URLs found for {base_url}. Try --type rss or --type sitemap explicitly.",
            err=True,
        )
        raise SystemExit(1)

    from aidar.core.ingestion import filter_prose_urls

    filtered_result = filter_prose_urls(urls, base_url=base_url)
    urls = filtered_result.kept
    if filtered_result.rejected:
        reasons = ", ".join(f"{key}={value}" for key, value in filtered_result.rejected.items())
        click.echo(f"Filtered {sum(filtered_result.rejected.values())} URLs ({reasons}).", err=True)

    # Optional caller-specific suffix allowlist after the shared prose policy.
    if filter_ext.strip():
        exts = [e.strip() for e in filter_ext.split(",") if e.strip()]
        filtered = [
            u for u in urls if any(u.endswith(e) or "/" in u.split(base_url)[-1] for e in exts)
        ]
        urls = filtered

    # Deduplicate, preserve order
    seen: set[str] = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    urls = deduped

    if limit > 0:
        urls = urls[:limit]

    click.echo(f"Returning {len(urls)} URLs.", err=True)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        click.echo(f"Saved to {output}", err=True)
    else:
        for url in urls:
            click.echo(url)
