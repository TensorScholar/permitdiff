"""Claude Code native-settings CLI surface."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from permitdiff.adapters.claude_code import ClaudeAdapterError, normalize_claude_preapproval_pair
from permitdiff.analysis import compare_policies
from permitdiff.corpus import load_corpus
from permitdiff.errors import CorpusLoadError, GateLoadError
from permitdiff.gate import GateConfig, evaluate_gate, strict_gate
from permitdiff.reporting import ReportBundle

app = typer.Typer(
    no_args_is_help=True,
    help="Compare bounded Claude Code project pre-approval changes from native settings.",
)
error_console = Console(stderr=True, width=160)
console = Console(width=160)


class ClaudeOutputFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"
    MARKDOWN = "markdown"
    SARIF = "sarif"


@app.command("compare")
def compare_claude(
    baseline: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    candidate: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    corpus: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    gate: Annotated[
        Path | None,
        typer.Option("--gate", exists=True, dir_okay=False, readable=True),
    ] = None,
    strict: Annotated[bool, typer.Option("--strict")] = False,
    output_format: Annotated[
        ClaudeOutputFormat,
        typer.Option("--format", case_sensitive=False),
    ] = ClaudeOutputFormat.CONSOLE,
    output: Annotated[Path | None, typer.Option("--output", "-o", dir_okay=False)] = None,
    evidence_output: Annotated[
        Path | None,
        typer.Option("--evidence-output", dir_okay=False),
    ] = None,
) -> None:
    """Compare native Claude ``dontAsk`` pre-approval changes with fail-closed semantics."""

    if gate is not None and strict:
        raise typer.BadParameter("--gate and --strict are mutually exclusive")
    if output is not None and output_format is ClaudeOutputFormat.CONSOLE:
        raise typer.BadParameter("--output requires json, markdown, or sarif format")

    try:
        pair = normalize_claude_preapproval_pair(baseline, candidate)
        scenarios = load_corpus(corpus)
        report = compare_policies(pair.baseline_policy, pair.candidate_policy, scenarios)
        gate_config = GateConfig.from_yaml(gate) if gate is not None else None
        if strict:
            gate_config = strict_gate()
        gate_result = evaluate_gate(report, gate_config) if gate_config is not None else None
    except (ClaudeAdapterError, CorpusLoadError, GateLoadError, ValueError) as exc:
        error_console.print(f"[red]Claude comparison failed[/red]: {exc}")
        raise typer.Exit(1) from exc

    if evidence_output is not None:
        try:
            evidence_output.parent.mkdir(parents=True, exist_ok=True)
            evidence_output.write_text(
                pair.evidence.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            error_console.print(f"[red]cannot write Claude adapter evidence[/red]: {exc}")
            raise typer.Exit(1) from exc
        console.print(f"wrote Claude adapter evidence to {evidence_output}")

    bundle = ReportBundle(report, gate_result)
    if output_format is ClaudeOutputFormat.CONSOLE:
        rendered = bundle.console()
    elif output_format is ClaudeOutputFormat.JSON:
        rendered = bundle.json()
    elif output_format is ClaudeOutputFormat.MARKDOWN:
        rendered = bundle.markdown()
    else:
        rendered = bundle.sarif(candidate)

    if output is None:
        typer.echo(rendered, nl=False)
    else:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            error_console.print(f"[red]cannot write report[/red]: {exc}")
            raise typer.Exit(1) from exc
        console.print(f"wrote {output_format.value} report to {output}")

    if gate_result is not None and not gate_result.passed:
        raise typer.Exit(2)
