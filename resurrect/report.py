from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from resurrect.gitinfo import GitFacts
from resurrect.scanner import RepoFacts

BANNER = r"""
           )
          ( )
          | |
       ___|_|___
      /  R.I.P  \
     |   README  |
     |    .md    |
     |___________|
   ~~~~~~~~~~~~~~~~~
"""

WEIGHTS = {"readme": 40, "setup": 20, "architecture": 20, "contributing": 20}
LABELS = {
    "readme": "README",
    "setup": "SETUP",
    "architecture": "ARCHITECTURE",
    "contributing": "CONTRIBUTING",
}
STEMS = {
    "setup": {"setup", "install", "installation", "getting-started", "getting_started", "quickstart"},
    "architecture": {"architecture", "design"},
    "contributing": {"contributing"},
}
DOC_SUFFIXES = {".md", ".rst", ".txt", ""}
STUB_BYTES = 500
ALIVE_DAYS = 180
DEAD_DAYS = 730


@dataclass(frozen=True)
class ExistingDoc:
    kind: str
    path: str | None
    stub: bool = False

    @property
    def missing(self) -> bool:
        return self.path is None or self.stub


def vitality(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < ALIVE_DAYS:
        return "alive"
    if days < DEAD_DAYS:
        return "dormant"
    return "dead"


def age_text(days: int) -> str:
    if days < 60:
        return f"{days} day{'s' if days != 1 else ''}"
    years, rest = divmod(days, 365)
    months = rest // 30
    if years == 0:
        human = f"{months} months"
    else:
        human = f"{years} year{'s' if years != 1 else ''}"
        if months:
            human += f", {months} month{'s' if months != 1 else ''}"
    return f"{human} ({days:,} days)"


def dependency_count(facts: RepoFacts) -> int:
    return len({name for names in facts.dependencies.values() for name in names})


def _find_doc(tree: list[str], stems: set[str]) -> str | None:
    for rel in sorted(tree, key=lambda r: (r.count("/"), r)):
        parts = rel.split("/")
        if len(parts) > 3:
            continue
        name = Path(parts[-1])
        if name.stem.lower() in stems and name.suffix.lower() in DOC_SUFFIXES:
            return rel
    return None


def find_existing_docs(facts: RepoFacts) -> list[ExistingDoc]:
    readme = facts.readme_file
    stub = False
    if readme:
        try:
            stub = (Path(facts.root) / readme).stat().st_size < STUB_BYTES
        except OSError:
            stub = False
    docs = [ExistingDoc("readme", readme, stub)]
    for kind in ("setup", "architecture", "contributing"):
        docs.append(ExistingDoc(kind, _find_doc(facts.tree, STEMS[kind])))
    return docs


def revival_score(docs: list[ExistingDoc]) -> int:
    return sum(WEIGHTS[d.kind] for d in docs if d.missing)


def print_banner(console: Console) -> None:
    console.print(Text(BANNER, style="yellow"))
    title = Text("README RESURRECTION", style="bold")
    title.append("   No documentation? Raise it from the dead.", style="italic")
    console.print(title)
    console.print()


def print_report(
    console: Console, facts: RepoFacts, git: GitFacts, docs: list[ExistingDoc]
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()

    table.add_row("Repository", Text(facts.name))

    if git.is_repo and git.days_since_last_commit is not None:
        state = vitality(git.days_since_last_commit)
        style = {"alive": "green", "dormant": "yellow", "dead": "bold red"}[state]
        condition = Text(state.upper(), style=style)
        condition.append(
            f" - last commit {git.last_commit_date[:10]}, "
            f"{age_text(git.days_since_last_commit)} ago"
        )
    elif git.is_repo:
        condition = Text("unknown (no commits)")
    else:
        condition = Text("unknown (not a git repository)")
    table.add_row("Condition", condition)

    if git.is_repo and git.total_commits:
        commits = f"{git.total_commits}+" if git.is_shallow else str(git.total_commits)
    else:
        commits = "unknown"
    table.add_row("Commits", Text(commits))

    langs = ", ".join(f"{k} ({v})" for k, v in list(facts.languages.items())[:5])
    table.add_row("Languages", Text(langs or "none detected"))
    table.add_row("Files", Text(f"{facts.file_count:,}"))
    deps = f"{dependency_count(facts)}"
    if facts.dependency_files:
        deps += f"  ({', '.join(facts.dependency_files[:3])})"
    table.add_row("Dependencies", Text(deps))

    table.add_row("", Text(""))
    for doc in docs:
        label = LABELS[doc.kind]
        if doc.path is None:
            status = Text("missing", style="red")
        elif doc.stub:
            status = Text(f"stub ({doc.path}, under {STUB_BYTES} bytes)", style="yellow")
        else:
            status = Text(f"found ({doc.path})", style="green")
        table.add_row(label, status)

    score = revival_score(docs)
    filled = score // 10
    bar = "#" * filled + "-" * (10 - filled)
    table.add_row("", Text(""))
    table.add_row(
        "Revival score",
        Text(f"{score}/100  {bar}  (higher = more documentation missing)", style="bold"),
    )

    console.print(Panel(table, title="Resurrection report", border_style="yellow", expand=False))