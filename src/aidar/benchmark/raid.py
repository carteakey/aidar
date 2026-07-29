from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from aidar.benchmark.manifest import BenchmarkManifest, Sample

_FIELDS = ("model", "domain", "attack", "decoding", "repetition_penalty")


def _selector(sample: Sample) -> dict[str, Any] | None:
    if sample.provenance.get("dataset") != "RAID":
        return None
    value = sample.provenance.get("selector")
    if not isinstance(value, dict):
        raise ValueError(f"RAID sample has no selector mapping: {sample.id}")
    missing = [field for field in _FIELDS if field not in value]
    if missing or not isinstance(value.get("ordinal"), int) or value["ordinal"] < 1:
        detail = ", ".join(missing) or "positive integer ordinal"
        raise ValueError(f"invalid RAID selector for {sample.id}: {detail}")
    return value


def import_raid(manifest: BenchmarkManifest, csv_path: Path) -> list[Path]:
    targets: list[tuple[Sample, dict[str, Any]]] = []
    for sample in manifest.samples:
        selector = _selector(sample)
        if selector is not None:
            if sample.source.kind != "file":
                raise ValueError(f"RAID sample must use a file source: {sample.id}")
            targets.append((sample, selector))
    if not targets:
        raise ValueError("manifest has no RAID samples")

    matches = {sample.id: 0 for sample, _ in targets}
    written: dict[str, Path] = {}
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {*_FIELDS, "generation"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"RAID CSV missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            for sample, selector in targets:
                if sample.id in written:
                    continue
                if all(row[field] == str(selector[field]) for field in _FIELDS):
                    matches[sample.id] += 1
                    if matches[sample.id] == selector["ordinal"]:
                        destination = Path(sample.source.location)
                        if not destination.is_absolute():
                            destination = manifest.path.parent / destination
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(row["generation"].strip() + "\n", encoding="utf-8")
                        written[sample.id] = destination.resolve()

    unresolved = [sample.id for sample, _ in targets if sample.id not in written]
    if unresolved:
        raise ValueError(f"RAID selectors did not match: {', '.join(unresolved)}")
    return [written[sample.id] for sample, _ in targets]
