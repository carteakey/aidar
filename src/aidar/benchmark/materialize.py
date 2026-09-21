from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aidar.benchmark.manifest import BenchmarkManifest, Sample
from aidar.core.fetcher import fetch_url, read_file


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_sample(sample: Sample, manifest_dir: Path) -> str:
    if sample.source.kind == "url":
        return fetch_url(sample.source.location).text
    source_path = Path(sample.source.location)
    if not source_path.is_absolute():
        source_path = manifest_dir / source_path
    return read_file(source_path).text


def materialize(
    manifest: BenchmarkManifest,
    data_dir: Path,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    corpus_dir = data_dir / manifest.id / manifest.version
    corpus_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    for sample in manifest.samples:
        destination = corpus_dir / f"{sample.id}.txt"
        if refresh or not destination.exists():
            text = _read_sample(sample, manifest.path.parent)
            destination.write_text(text.strip() + "\n", encoding="utf-8")
        text = destination.read_text(encoding="utf-8")
        entries.append(
            {
                "id": sample.id,
                "path": destination.name,
                "sha256": _sha256(text),
                "bytes": len(text.encode("utf-8")),
                "words": len(text.split()),
                "source_kind": sample.source.kind,
                "source": sample.source.location,
            }
        )

    lock = {
        "schema_version": 1,
        "benchmark": {"id": manifest.id, "version": manifest.version},
        "samples": entries,
    }
    (corpus_dir / "lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return lock


def verify_materialized(manifest: BenchmarkManifest, data_dir: Path) -> dict[str, Path]:
    corpus_dir = data_dir / manifest.id / manifest.version
    lock_path = corpus_dir / "lock.json"
    if not lock_path.exists():
        raise ValueError(f"materialization lock not found: {lock_path}")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    locked = {entry["id"]: entry for entry in lock.get("samples", [])}
    resolved: dict[str, Path] = {}
    for sample in manifest.samples:
        entry = locked.get(sample.id)
        if entry is None:
            raise ValueError(f"sample missing from lock: {sample.id}")
        path = corpus_dir / entry["path"]
        if not path.exists():
            raise ValueError(f"materialized sample missing: {path}")
        actual = _sha256(path.read_text(encoding="utf-8"))
        if actual != entry["sha256"]:
            raise ValueError(f"checksum mismatch for sample: {sample.id}")
        resolved[sample.id] = path
    return resolved
