from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml

Label = Literal["human", "ai_generated", "mixed"]
Split = Literal["validation", "holdout"]
SourceKind = Literal["file", "url"]


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    kind: SourceKind
    location: str


@dataclass(frozen=True)
class Sample:
    id: str
    label: Label
    split: Split
    topic: str
    language: str
    publisher: str
    published_at: str | None
    source: Source
    provenance: dict[str, Any]
    segments: dict[str, str]


@dataclass(frozen=True)
class BenchmarkManifest:
    schema_version: int
    id: str
    version: str
    description: str
    samples: tuple[Sample, ...]
    path: Path


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{field} must be a mapping")
    return cast(dict[str, Any], value)


def _required_string(data: dict[str, Any], field: str, context: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{context}.{field} must be a non-empty string")
    return value.strip()


def load_manifest(path: Path) -> BenchmarkManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError(f"could not read manifest: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML: {exc}") from exc

    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")
    benchmark = _mapping(root.get("benchmark"), "benchmark")
    benchmark_id = _required_string(benchmark, "id", "benchmark")
    version = _required_string(benchmark, "version", "benchmark")
    description = _required_string(benchmark, "description", "benchmark")
    raw_samples = root.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ManifestError("samples must be a non-empty list")

    samples: list[Sample] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_samples):
        context = f"samples[{index}]"
        data = _mapping(item, context)
        sample_id = _required_string(data, "id", context)
        if sample_id in seen:
            raise ManifestError(f"duplicate sample id: {sample_id}")
        seen.add(sample_id)

        label = data.get("label")
        if label not in {"human", "ai_generated", "mixed"}:
            raise ManifestError(f"{context}.label must be human, ai_generated, or mixed")
        split = data.get("split")
        if split not in {"validation", "holdout"}:
            raise ManifestError(f"{context}.split must be validation or holdout")

        source_data = _mapping(data.get("source"), f"{context}.source")
        kind = source_data.get("kind")
        if kind not in {"file", "url"}:
            raise ManifestError(f"{context}.source.kind must be file or url")
        location_field = "path" if kind == "file" else "url"
        location = _required_string(source_data, location_field, f"{context}.source")

        provenance = _mapping(data.get("provenance"), f"{context}.provenance")
        _required_string(provenance, "evidence", f"{context}.provenance")
        if label == "ai_generated":
            _required_string(provenance, "model_family", f"{context}.provenance")
            _required_string(provenance, "model", f"{context}.provenance")
        if label == "mixed":
            _required_string(provenance, "editing_method", f"{context}.provenance")
        if provenance.get("dataset") == "RAID":
            selector = _mapping(provenance.get("selector"), f"{context}.provenance.selector")
            for field in ("model", "domain", "attack", "decoding", "repetition_penalty"):
                _required_string(selector, field, f"{context}.provenance.selector")
            ordinal = selector.get("ordinal")
            if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
                raise ManifestError(
                    f"{context}.provenance.selector.ordinal must be a positive integer"
                )

        raw_segments = data.get("segments", {})
        segments_data = _mapping(raw_segments, f"{context}.segments")
        segments = {str(key): str(value) for key, value in segments_data.items()}
        samples.append(
            Sample(
                id=sample_id,
                label=cast(Label, label),
                split=cast(Split, split),
                topic=_required_string(data, "topic", context),
                language=_required_string(data, "language", context),
                publisher=_required_string(data, "publisher", context),
                published_at=cast(str | None, data.get("published_at")),
                source=Source(kind=cast(SourceKind, kind), location=location),
                provenance=provenance,
                segments=segments,
            )
        )

    return BenchmarkManifest(
        schema_version=1,
        id=benchmark_id,
        version=version,
        description=description,
        samples=tuple(samples),
        path=path.resolve(),
    )
