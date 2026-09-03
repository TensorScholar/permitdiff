"""PermitDiff command-line interface."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from permitdiff._version import __version__
from permitdiff.analysis import compare_policies
from permitdiff.claude_cli import app as claude_app
from permitdiff.corpus import load_corpus
from permitdiff.errors import CorpusLoadError, GateLoadError, PolicyLoadError
from permitdiff.gate import GateConfig, evaluate_gate, strict_gate
from permitdiff.policy import PolicyDocument
from permitdiff.reporting import ReportBundle
from permitdiff.resources import write_starter

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Review effective AI-agent permission changes before release.",
)
policy_app = typer.Typer(no_args_is_help=True, help="Validate and inspect policies.")
corpus_app = typer.Typer(no_args_is_help=True, help="Validate scenario corpora.")
app.add_typer(policy_app, name="policy")
app.add_typer(corpus_app, name="corpus")
app.add_typer(claude_app, name="claude")
console = Console(width=160)
error_console = Console(stderr=True, width=160)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"permitdiff {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = None,
) -> None:
    """Review effective AI-agent permission changes before release."""
    del version


class OutputFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"
    MARKDOWN = "markdown"
    SARIF = "sarif"


@app.command()
def init(
    destination: Annotated[Path, typer.Argument()] = Path("permitdiff-starter"),
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Create a minimal, reviewable PermitDiff project."""

    try:
        written = write_starter(destination, force=force)
    except (FileExistsError, OSError) as exc:
        error_console.print(f"[red]init failed[/red]: {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]created[/green] {destination}")
    for path in written:
        console.print(f"  {path.relative_to(destination)}")
    console.print(
        "Run: permitdiff compare policies/baseline.yaml policies/candidate.yaml "
        "corpus.jsonl --gate permitdiff-gate.yaml"
    )


@policy_app.command("validate")
def validate_policy(
    policy: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate a policy and print its immutable digest."""

    try:
        document = PolicyDocument.from_yaml(policy)
    except PolicyLoadError as exc:
        error_console.print(f"[red]invalid[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]valid[/green] {document.metadata.name} {document.metadata.version}")
    console.print(f"sha256:{document.digest()}")


@policy_app.command("show")
def show_policy(
    policy: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Render ordered rules and effects."""

    try:
        document = PolicyDocument.from_yaml(policy)
    except PolicyLoadError as exc:
        error_console.print(f"[red]invalid[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"{document.metadata.name} {document.metadata.version}")
    table.add_column("Order", justify="right")
    table.add_column("Rule")
    table.add_column("Effect")
    table.add_column("Tools")
    table.add_column("Description")
    for index, rule in enumerate(document.rules, start=1):
        table.add_row(
            str(index),
            rule.id,
            rule.effect.value,
            ", ".join(rule.match.tools),
            rule.description,
        )
    table.caption = f"default: {document.default_effect.value} · sha256:{document.digest()[:12]}"
    console.print(table)


@corpus_app.command("validate")
def validate_corpus(
    corpus: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate JSONL scenarios and print a risk distribution."""

    try:
        scenarios = load_corpus(corpus)
    except CorpusLoadError as exc:
        error_console.print(f"[red]invalid[/red] {exc}")
        raise typer.Exit(1) from exc
    by_risk: dict[str, int] = {}
    for scenario in scenarios:
        by_risk[scenario.risk.value] = by_risk.get(scenario.risk.value, 0) + 1
    console.print(f"[green]valid[/green] {len(scenarios)} scenarios")
    console.print(" · ".join(f"{risk}={count}" for risk, count in sorted(by_risk.items())))


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    candidate: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    corpus: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    gate: Annotated[
        Path | None,
        typer.Option("--gate", exists=True, dir_okay=False, readable=True),
    ] = None,
    strict: Annotated[bool, typer.Option("--strict")] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", case_sensitive=False),
    ] = OutputFormat.CONSOLE,
    output: Annotated[Path | None, typer.Option("--output", "-o", dir_okay=False)] = None,
) -> None:
    """Compare effective permissions and optionally enforce a release gate."""

    if gate is not None and strict:
        raise typer.BadParameter("--gate and --strict are mutually exclusive")
    if output is not None and output_format is OutputFormat.CONSOLE:
        raise typer.BadParameter("--output requires json, markdown, or sarif format")

    try:
        baseline_policy = PolicyDocument.from_yaml(baseline)
        candidate_policy = PolicyDocument.from_yaml(candidate)
        scenarios = load_corpus(corpus)
        report = compare_policies(baseline_policy, candidate_policy, scenarios)
        gate_config = GateConfig.from_yaml(gate) if gate is not None else None
        if strict:
            gate_config = strict_gate()
        gate_result = evaluate_gate(report, gate_config) if gate_config is not None else None
    except (PolicyLoadError, CorpusLoadError, GateLoadError, ValueError) as exc:
        error_console.print(f"[red]comparison failed[/red]: {exc}")
        raise typer.Exit(1) from exc

    bundle = ReportBundle(report, gate_result)
    if output_format is OutputFormat.CONSOLE:
        rendered = bundle.console()
    elif output_format is OutputFormat.JSON:
        rendered = bundle.json()
    elif output_format is OutputFormat.MARKDOWN:
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


if __name__ == "__main__":  # pragma: no cover
    app()
