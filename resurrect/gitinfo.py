from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class GitFacts:
    is_repo: bool = False
    last_commit_date: str | None = None
    first_commit_date: str | None = None
    last_commit_message: str | None = None
    total_commits: int = 0
    days_since_last_commit: int | None = None
    top_contributors: list[str] = field(default_factory=list)
    is_shallow: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _git(root: Path, *args: str) -> str | None:
    """Run a git command in root. Return stdout, or None if it fails."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _parse_shortlog(text: str, limit: int = 5) -> list[str]:
    names = []
    for line in text.splitlines():
        parts = line.strip().split("\t", 1)
        if len(parts) == 2 and parts[1].strip():
            names.append(parts[1].strip())
    return names[:limit]


def get_git_facts(path: str | Path) -> GitFacts:
    root = Path(path).resolve()
    facts = GitFacts()

    if _git(root, "rev-parse", "--is-inside-work-tree") != "true":
        return facts
    facts.is_repo = True
    facts.is_shallow = _git(root, "rev-parse", "--is-shallow-repository") == "true"

    last = _git(root, "log", "-1", "--format=%cI")
    if not last:  # repo exists but has no commits
        return facts
    facts.last_commit_date = last
    facts.last_commit_message = _git(root, "log", "-1", "--format=%s")

    dates = _git(root, "log", "--format=%cI")
    if dates:
        facts.first_commit_date = dates.splitlines()[-1]

    count = _git(root, "rev-list", "--count", "HEAD")
    facts.total_commits = int(count) if count and count.isdigit() else 0

    shortlog = _git(root, "shortlog", "-sn", "HEAD")
    if shortlog:
        facts.top_contributors = _parse_shortlog(shortlog)

    try:
        last_dt = datetime.fromisoformat(last)
        facts.days_since_last_commit = (datetime.now(timezone.utc) - last_dt).days
    except ValueError:
        pass

    return facts


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(get_git_facts(target).to_dict(), indent=2))