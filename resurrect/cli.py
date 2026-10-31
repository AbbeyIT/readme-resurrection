import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.text import Text

from resurrect.docs import DOCS, generate_doc, write_doc
from resurrect.fetch import CloneError, open_repo
from resurrect.gitinfo import get_git_facts
from resurrect.llm import DEFAULT_MODEL, LLMConfig, LLMError, check_ollama
from resurrect.report import find_existing_docs, print_banner, print_report
from resurrect.scanner import scan
from resurrect.summarize import select_files, summarize_repo
from resurrect.verify import annotate_doc, verify_doc

app = typer.Typer(help="README Resurrection: raise dead repos from the grave.")


def _duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _fail(console: Console, message: str) -> None:
    console.print(f"Error: {message}", style="bold red", markup=False)
    raise typer.Exit(code=1)


def _summarize(console: Console, facts, cfg: LLMConfig, max_files: int) -> dict[str, str]:
    total = len(select_files(facts, max_files=max_files))
    if total == 0:
        console.print("No source files found to summarize; documents will use repository facts only.")
        return {}
    columns = (SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn())
    with Progress(*columns, console=console) as progress:
        task = progress.add_task("Reading the remains", total=total)

        def update(done: int, _total: int, rel: str, cached: bool) -> None:
            note = " (cached)" if cached else ""
            progress.update(task, completed=done, description=escape(f"Read {rel}{note}"))

        return summarize_repo(facts, cfg, max_files=max_files, on_progress=update)


def _write_docs(console, kinds, facts, git, summaries, cfg, out_dir: Path, verify: bool):
    rows = []
    for kind in kinds:
        spec = DOCS[kind]
        count = [0]
        started = time.perf_counter()
        with console.status(f"Writing {spec.filename}...") as status:

            def on_token(_token: str, status=status, count=count, name=spec.filename) -> None:
                count[0] += 1
                status.update(f"Writing {name}... {count[0]} tokens")

            text = generate_doc(kind, facts, git, summaries, cfg, on_token=on_token)
        issues = verify_doc(text, facts) if verify else []
        final = annotate_doc(text, issues) if verify else text
        path = write_doc(out_dir, spec.filename, final)
        elapsed = time.perf_counter() - started
        console.print(f"Wrote {path.name} in {_duration(elapsed)}", markup=False, highlight=False)
        rows.append((spec.filename, path, len(issues)))
    return rows


def _print_summary(console: Console, rows, out_dir: Path, elapsed: float, verify: bool) -> None:
    table = Table(title="Documents raised from the dead")
    table.add_column("Document")
    table.add_column("Saved to")
    table.add_column("Needs review")
    flagged = 0
    for filename, path, issues in rows:
        flagged += issues
        if not verify:
            review = Text("not checked", style="dim")
        elif issues:
            review = Text(f"{issues} item(s)", style="yellow")
        else:
            review = Text("none", style="green")
        table.add_row(Text(filename), Text(str(path)), review)
    console.print()
    console.print(table)
    console.print(f"\nDone in {_duration(elapsed)}. Files are in {out_dir}", markup=False, highlight=False)
    if flagged:
        console.print(
            "Items under 'Needs review' could not be checked against the repository. "
            "Read them before publishing.",
            markup=False,
            highlight=False,
        )


@app.command()
def main(
    target: str = typer.Argument(..., help="Local path or GitHub URL of the repo"),
    out: str = typer.Option("./resurrected", help="Output folder"),
    model: str = typer.Option(DEFAULT_MODEL, help="Ollama model name"),
    max_files: int = typer.Option(8, "--max-files", help="Maximum source files to summarize"),
    skip: list[str] = typer.Option(
        [], "--skip", help="Document to skip: readme, setup, architecture, contributing (repeatable)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the Resurrection report only; no model calls"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip the verification pass"),
):
    """Analyze a repository and generate missing documentation.

    Scans the code, summarizes key files with a local Ollama model, writes README,
    SETUP, ARCHITECTURE and CONTRIBUTING files, and flags anything it could not verify.
    """
    unknown = [name for name in skip if name not in DOCS]
    if unknown:
        raise typer.BadParameter(
            f"Unknown document(s): {', '.join(unknown)}. Choose from: {', '.join(DOCS)}.",
            param_hint="--skip",
        )
    kinds = [kind for kind in DOCS if kind not in skip]

    try:  # keep the unicode-safe output on Windows consoles
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    console = Console()
    started = time.perf_counter()
    cfg = LLMConfig(model=model)
    out_dir = Path(out).expanduser().resolve()
    verify = not no_verify

    print_banner(console)
    try:
        if not dry_run and kinds:
            check_ollama(cfg)
        with open_repo(target) as (folder, _name):
            facts = scan(folder)
            git = get_git_facts(folder)
            print_report(console, facts, git, find_existing_docs(facts))
            if dry_run:
                console.print("\nDry run: no documents were generated.")
                return
            if not kinds:
                console.print("\nEvery document was skipped; nothing to generate.")
                return
            summaries = _summarize(console, facts, cfg, max_files)
            rows = _write_docs(console, kinds, facts, git, summaries, cfg, out_dir, verify)
    except (CloneError, LLMError) as exc:
        _fail(console, str(exc))
    except KeyboardInterrupt:
        console.print("\nInterrupted. Finished summaries are cached, so a re-run will be quicker.")
        raise typer.Exit(code=130)
    _print_summary(console, rows, out_dir, time.perf_counter() - started, verify)


if __name__ == "__main__":
    app()