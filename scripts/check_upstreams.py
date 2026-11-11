#!/usr/bin/env python3
"""Report drift between sources.yaml and the upstreams it pins.

Read-only: prints what changed and how to refresh; never edits files.

    python scripts/check_upstreams.py             # report, exit 0
    python scripts/check_upstreams.py --strict    # exit 1 if anything drifted
                                                  # or the manifest disagrees
                                                  # with the pattern files

Standard library only. Uses GITHUB_TOKEN if set (unauthenticated GitHub API
allows 60 req/hour). Wikipedia pins are checked against the MediaWiki API.

The manifest is sources.yaml at the repo root; its `derived_patterns` lists
are cross-checked against the `references:` fields of patterns/*.yaml, so a
hand-edit to either side that forgets the other fails under --strict.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB_API = "https://api.github.com"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
TIMEOUT = 30


# ---------------------------------------------------------------- manifest --

def load_manifest(path: Path) -> list[dict]:
    """Parse the sources.yaml subset: flat entries, block lists, no nesting."""
    entries: list[dict] | None = None
    entry: dict | None = None
    listkey: str | None = None

    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = re.sub(r"\s+#.*$", "", raw.rstrip())
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("- "):
            if indent == 2:
                if entries is None:
                    raise SystemExit(f"{path}:{lineno}: expected a top-level 'sources:' list")
                entry = {}
                entries.append(entry)
                listkey = None
                stripped = stripped[2:]
            elif listkey is not None and entry is not None:
                entry.setdefault(listkey, []).append(_scalar(stripped[2:], path, lineno))
                continue
            else:
                raise SystemExit(f"{path}:{lineno}: unexpected list item: {raw!r}")

        if ":" not in stripped:
            raise SystemExit(f"{path}:{lineno}: expected 'key: value', got {raw!r}")
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if indent == 0:
            if key != "sources":
                raise SystemExit(f"{path}:{lineno}: unexpected top-level key {key!r}")
            entries = []
            entry = None
            continue
        if entry is None:
            raise SystemExit(f"{path}:{lineno}: key {key!r} outside a source entry")
        if value == "[]":
            entry[key] = []
            listkey = None
        elif value == "":
            entry[key] = []
            listkey = key
        else:
            entry[key] = _scalar(value, path, lineno)
            listkey = None

    if entries is None:
        raise SystemExit(f"{path}: no 'sources:' list found")
    return entries


def _scalar(value: str, path: Path, lineno: int) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if value == "null":
        return None
    if "#" in value:  # values must not smuggle comments past the stripper
        raise SystemExit(f"{path}:{lineno}: quote this value or drop the '#': {value!r}")
    return value


# ------------------------------------------------- pattern references scan --

REF_RE = re.compile(r"^(references:)$")


def pattern_references(patterns_dir: Path) -> dict[str, set[str]]:
    """pattern id -> set of reference URLs, from patterns/**/*.yaml."""
    out: dict[str, set[str]] = {}
    for path in sorted(patterns_dir.rglob("*.yaml")):
        pid, urls, in_refs = None, set(), False
        for raw in path.read_text().splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            if not raw[0].isspace():  # top-level key
                in_refs = bool(REF_RE.match(raw))
                if raw.startswith("id:"):
                    pid = raw.partition(":")[2].strip()
                continue
            if in_refs and raw.strip().startswith("- "):
                urls.add(raw.strip()[2:].strip())
        if pid and urls:
            out[pid] = urls
    return out


def effective_url(source: dict) -> str:
    """The URL pattern citations are matched against: `url` if set, else a
    locator that already is a URL (web sources carry the page in locator)."""
    url = source.get("url")
    if not url:
        locator = str(source.get("locator", ""))
        url = locator if locator.startswith("http") else ""
    return url.rstrip("/") if url else ""


def reference_maps_to(ref: str, source: dict) -> bool:
    url = effective_url(source)
    if not url:
        return False
    return ref.rstrip("/") == url or ref.rstrip("/").startswith(url + "/")


# ---------------------------------------------------------------- network --

def http_json(url: str, token: str | None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "aidar-check-upstreams"}
    # Only GitHub's API understands a GitHub token; sending it elsewhere
    # (MediaWiki) causes a 401.
    if token and urllib.parse.urlsplit(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode())


def version_parts(tag: str, prefix: str) -> list:
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-]", re.sub(r"^v", "", tag[len(prefix):]))]


def compare_tags(a: str, b: str, prefix: str) -> int:
    pa, pb = version_parts(a, prefix), version_parts(b, prefix)
    for i in range(max(len(pa), len(pb))):
        x, y = (pa[i] if i < len(pa) else 0), (pb[i] if i < len(pb) else 0)
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return x - y
        return (str(x) > str(y)) - (str(x) < str(y))
    return 0


def latest_tag(source: dict, token: str | None) -> str:
    prefix = source.get("tag_prefix") or ""
    tags: list[str] = []
    for page in range(1, 6):
        batch = http_json(f"{GITHUB_API}/repos/{source['locator']}/tags?per_page=100&page={page}", token)
        tags.extend(t["name"] for t in batch)
        if len(batch) < 100:
            break
    matching = [t for t in tags if t.startswith(prefix) and re.search(r"\d", t[len(prefix):])]
    if not matching:
        raise RuntimeError(f"no tags matching {prefix!r} in {source['locator']}")
    return max(matching, key=lambda t: version_parts(t, prefix))


def check(source: dict, token: str | None) -> tuple[bool, str, str]:
    """Return (drifted, latest, link). Raises RuntimeError on API trouble."""
    kind = source["kind"]
    if kind == "git-tag":
        prefix = source.get("tag_prefix") or ""
        latest = latest_tag(source, token)
        drift = compare_tags(latest, source["pinned"], prefix) > 0
        link = (f"https://github.com/{source['locator']}/compare/{source['pinned']}...{latest}" if drift
                else f"https://github.com/{source['locator']}/releases/tag/{latest}")
        return drift, latest, link
    if kind == "gist":
        gist = http_json(f"{GITHUB_API}/gists/{source['locator']}", token)
        drift = _ts(gist["updated_at"]) > _ts(source["pinned"])
        return drift, gist["updated_at"], f"{gist['html_url']}/revisions"
    if kind == "wikipedia":
        params = urllib.parse.urlencode({
            "action": "query", "prop": "revisions", "titles": source["locator"],
            "format": "json", "formatversion": "2",
        })
        data = http_json(f"{MEDIAWIKI_API}?{params}", token)
        page = data["query"]["pages"][0]
        latest = str(page["revisions"][0]["revid"])
        drift = latest != str(source["pinned"])
        link = (f"https://en.wikipedia.org/w/index.php?title={urllib.parse.quote(source['locator'])}"
                f"&diff={latest}&oldid={source['pinned']}") if drift else f"{source['url']}?oldid={latest}"
        return drift, latest, link
    raise RuntimeError(f"cannot drift-check kind {kind!r}")


def _ts(value: str):
    return value.replace("Z", "+00:00")


# ------------------------------------------------------------------ main --

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=ROOT / "sources.yaml")
    ap.add_argument("--patterns-dir", type=Path, default=ROOT / "patterns")
    ap.add_argument("--strict", action="store_true", help="exit 1 on drift or manifest/pattern mismatch")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    sources = load_manifest(args.manifest)
    drifted = failed = unchecked = 0

    # Offline integrity: manifest vs the pattern files it claims to serve.
    refs = pattern_references(args.patterns_dir) if args.patterns_dir.is_dir() else {}
    if not refs:
        print(f"WARN   no pattern references found under {args.patterns_dir}")
    derived: dict[str, set[str]] = {}
    for src in sources:
        for pid in src.get("derived_patterns") or []:
            derived.setdefault(pid, set()).add(src["id"])
    known = set(refs)
    for pid, urls in sorted(refs.items()):
        expected = {s["id"] for s in sources if effective_url(s) and any(reference_maps_to(u, s) for u in urls)}
        missing = {u for u in urls if not any(reference_maps_to(u, s) for s in sources)}
        if pid not in derived:
            print(f"FAIL   pattern {pid} cites {sorted(urls)} but no source lists it in derived_patterns")
            failed += 1
        elif derived[pid] != expected:
            print(f"FAIL   pattern {pid}: manifest says {sorted(derived[pid])}, references imply {sorted(expected)}")
            failed += 1
        elif missing:
            print(f"FAIL   pattern {pid} cites untracked URL(s): {sorted(missing)}")
            failed += 1
    for src in sources:
        for pid in src.get("derived_patterns") or []:
            if pid not in known:
                print(f"FAIL   source {src['id']}: derived pattern {pid!r} does not exist under {args.patterns_dir}")
                failed += 1
    if refs:
        print(f"manifest ok: {len(refs)} patterns cross-checked against {len(sources)} sources")

    for src in sources:
        if src.get("pinned") is None:
            print(f"unpinned {src['id']}: {src['kind']}, citation only")
            continue
        try:
            drift, latest, link = check(src, token)
        except (RuntimeError, OSError, KeyError, ValueError) as err:
            # Unchecked is not drift: a network blip or rate limit must not
            # file a false "sources drifted" issue in CI.
            unchecked += 1
            print(f"WARN   {src['id']}: could not check ({err})")
            continue
        if drift:
            drifted += 1
            print(f"DRIFT  {src['id']}: pinned {src['pinned']} -> upstream {latest}")
            print(f"       {link}")
            print("       update pinned in sources.yaml only after reviewing the change")
        else:
            print(f"ok     {src['id']}: {src['pinned']}")

    checked = sum(1 for s in sources if s.get("pinned") is not None)
    print(f"\n{len(sources)} sources, {checked} pinned, {drifted} drifted, "
          f"{failed} manifest errors, {unchecked} unchecked.")
    if args.strict and (drifted or failed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
