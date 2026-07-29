from __future__ import annotations

from pathlib import Path

import click

from aidar.benchmark.evaluate import evaluate, write_report
from aidar.benchmark.manifest import ManifestError, load_manifest
from aidar.benchmark.materialize import materialize, verify_materialized
from aidar.benchmark.raid import import_raid
from aidar.cli.main import aidar


@aidar.group()
def benchmark() -> None:
    """Validate, materialize, and evaluate labeled benchmark manifests."""


@benchmark.command("validate")
@click.argument("manifest", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def validate_command(manifest: Path, data_dir: Path | None) -> None:
    """Validate a manifest and optionally verify its materialized checksums."""
    try:
        loaded = load_manifest(manifest)
        if data_dir is not None:
            verify_materialized(loaded, data_dir)
    except (ManifestError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Valid: {loaded.id} {loaded.version} ({len(loaded.samples)} samples)")


@benchmark.command("materialize")
@click.argument("manifest", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--data-dir", type=click.Path(path_type=Path), default=Path(".benchmark-data"), show_default=True)
@click.option("--refresh", is_flag=True, help="Refetch or recopy samples that already exist.")
def materialize_command(manifest: Path, data_dir: Path, refresh: bool) -> None:
    """Fetch or copy raw samples into the ignored benchmark data directory."""
    try:
        loaded = load_manifest(manifest)
        lock = materialize(loaded, data_dir, refresh=refresh)
    except (ManifestError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Materialized {len(lock['samples'])} samples")


@benchmark.command("import-raid")
@click.argument("manifest", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.argument("raid_csv", type=click.Path(path_type=Path, exists=True, dir_okay=False))
def import_raid_command(manifest: Path, raid_csv: Path) -> None:
    """Export manifest-selected generations from a RAID CSV file."""
    try:
        loaded = load_manifest(manifest)
        written = import_raid(loaded, raid_csv)
    except (ManifestError, ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Imported {len(written)} RAID samples")


@benchmark.command("run")
@click.argument("manifest", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--data-dir", type=click.Path(path_type=Path), default=Path(".benchmark-data"), show_default=True)
@click.option("--report-dir", type=click.Path(path_type=Path), default=Path("benchmark-reports"), show_default=True)
@click.option("--split", type=click.Choice(["validation", "holdout", "all"]), default="holdout", show_default=True)
@click.option("--seed", type=int, default=1729, show_default=True)
@click.option("--bootstrap-iterations", type=click.IntRange(min=1), default=1000, show_default=True)
@click.option("--materialize/--no-materialize", "should_materialize", default=True, show_default=True)
@click.option("--refresh", is_flag=True, help="Refetch or recopy materialized samples.")
@click.pass_context
def run_command(
    ctx: click.Context,
    manifest: Path,
    data_dir: Path,
    report_dir: Path,
    split: str,
    seed: int,
    bootstrap_iterations: int,
    should_materialize: bool,
    refresh: bool,
) -> None:
    """Materialize and evaluate a benchmark in one reproducible command."""
    try:
        loaded = load_manifest(manifest)
        if should_materialize:
            materialize(loaded, data_dir, refresh=refresh)
        report = evaluate(
            loaded,
            data_dir,
            ctx.obj["analyzer"],
            ctx.obj["config"],
            split=split,
            seed=seed,
            bootstrap_iterations=bootstrap_iterations,
        )
        json_path, markdown_path = write_report(report, report_dir / loaded.id / loaded.version / split)
    except (ManifestError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote {json_path} and {markdown_path}")
