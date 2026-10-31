from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from resurrect.docs import known_commands
from resurrect.scanner import MAX_TREE, SKIP_DIRS, RepoFacts

NEEDS_REVIEW = "## Needs review"
SHELL_LANGS = {"", "sh", "bash", "shell", "console", "bat", "cmd", "powershell", "zsh"}
COMMAND_WORDS = {
    "pip", "pip3", "python", "python3", "npm", "npx", "yarn", "pnpm", "make", "cargo",
    "go", "mvn", "bundle", "gem", "git", "docker", "node", "pytest", "uv", "poetry",
}
FILE_EXTENSIONS = {
    "py", "js", "jsx", "ts", "tsx", "json", "toml", "md", "txt", "yml", "yaml", "cfg",
    "ini", "xml", "gradle", "go", "rs", "java", "rb", "php", "sh", "c", "h", "cpp", "cs",
    "kt", "swift", "html", "css", "lock", "groovy", "lua", "pl",
}
BARE_FILES = {"LICENSE", "Makefile", "Dockerfile", "README", "COPYING", "Pipfile", "Gemfile"}
INLINE = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class Issue:
    kind: str  # "path", "command" or "import"
    text: str
    line: int

    @property
    def message(self) -> str:
        if self.kind == "path":
            return f"Path `{self.text}` was not found in the repository (line {self.line})"
        if self.kind == "command":
            return (
                f"Command `{self.text}` is not backed by the repository's files "
                f"(line {self.line})"
            )
        subject, target = self.text.split(" -> ")
        return (
            f"`{subject}` is not shown importing `{target}` in the code (line {self.line})"
        )


class _Index:
    def __init__(self, facts: RepoFacts) -> None:
        self.name = facts.name
        self.files = set(facts.tree)
        self.dirs: set[str] = set()
        self.base: dict[str, list[str]] = {}
        for rel in facts.tree:
            parts = rel.split("/")
            for i in range(1, len(parts)):
                self.dirs.add("/".join(parts[:i]))
            self.base.setdefault(parts[-1], []).append(rel)
        self.tops = {rel.split("/")[0] for rel in facts.tree}

    @staticmethod
    def clean(token: str) -> str:
        return token.removeprefix("./").rstrip("/")

    def resolve(self, token: str) -> str | None:
        """Map a mentioned path to one real file or folder, or None."""
        p = self.clean(token)
        if p in self.files or p in self.dirs:
            return p
        if "/" not in p and len(self.base.get(p, [])) == 1:
            return self.base[p][0]
        return None

    def exists(self, token: str) -> bool:
        p = self.clean(token)
        if self.resolve(token) is not None:
            return True
        if "/" not in p and p in self.base:
            return True
        return p in SKIP_DIRS or p == self.name

    def looks_like_path(self, token: str) -> bool:
        if not token or " " in token or "\\" in token or "://" in token:
            return False
        if any(c in token for c in "<>*{}$=|") or token.startswith(("-", "@")):
            return False
        if "/" in token:
            last = token.rstrip("/").rsplit("/", 1)[-1]
            ext = last.rsplit(".", 1)[-1].lower() if "." in last else ""
            first = self.clean(token).split("/")[0]
            return token.endswith("/") or ext in FILE_EXTENSIONS or first in self.tops
        if token in BARE_FILES:
            return True
        if token.startswith(".") and len(token) > 1 and token[1].isalpha():
            return True
        ext = token.rsplit(".", 1)[-1].lower() if "." in token else ""
        return ext in FILE_EXTENSIONS


def _norm(command: str) -> str:
    return " ".join(command.split())


def _unverified_commands(line: str, known: set[str], cli_names: set[str]) -> list[str]:
    line = line.strip()
    if not line or line.startswith("#"):
        return []
    line = line.removeprefix("$ ").removeprefix("> ")
    bad = []
    for part in re.split(r"\s*(?:&&|;)\s*", line):
        words = part.split()
        if words and (words[0] in COMMAND_WORDS or words[0] in cli_names):
            if _norm(part) not in known:
                bad.append(part.strip())
    return bad


def _import_issues(line: str, number: int, facts: RepoFacts, idx: _Index) -> list[Issue]:
    if " imports " not in line:
        return []
    left, right = line.split(" imports ", 1)
    subjects = INLINE.findall(left)
    targets = INLINE.findall(right)
    if not subjects or not targets:
        return []
    subject = idx.resolve(subjects[-1])
    if subject is None or not subject.endswith(".py"):
        return []
    actual = set(facts.imports.get(subject, []))
    issues = []
    for token in targets:
        target = idx.resolve(token)
        if target is not None and target not in actual:
            issues.append(Issue("import", f"{subject} -> {target}", number))
    return issues


def verify_doc(text: str, facts: RepoFacts) -> list[Issue]:
    idx = _Index(facts)
    known = {_norm(c) for c in known_commands(facts)}
    cli_names = set(facts.cli_commands)
    check_paths = len(facts.tree) < MAX_TREE  # a truncated tree cannot prove absence
    check_imports = any(p.endswith(".py") for p in facts.tree)

    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, token: str, number: int) -> None:
        if (kind, token) not in seen:
            seen.add((kind, token))
            issues.append(Issue(kind, token, number))

    in_fence = False
    lang = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            lang = stripped[3:].strip().lower() if in_fence else ""
            continue
        if stripped.startswith(NEEDS_REVIEW):
            break
        if in_fence:
            if lang in SHELL_LANGS:
                for command in _unverified_commands(raw, known, cli_names):
                    add("command", command, number)
            continue
        for token in INLINE.findall(raw):
            if " " in token:
                for command in _unverified_commands(token, known, cli_names):
                    add("command", command, number)
            elif check_paths and idx.looks_like_path(token) and not idx.exists(token):
                add("path", token, number)
        if check_imports:
            for issue in _import_issues(raw, number, facts, idx):
                add(issue.kind, issue.text, issue.line)
    return issues


def strip_review(text: str) -> str:
    """Remove a previous 'Needs review' section so re-running never stacks them."""
    if text.startswith(NEEDS_REVIEW):
        return ""
    i = text.find("\n" + NEEDS_REVIEW)
    return text[:i].rstrip() + "\n" if i != -1 else text


def annotate_doc(text: str, issues: list[Issue]) -> str:
    base = strip_review(text)
    if not issues:
        return base
    lines = [
        "",
        NEEDS_REVIEW,
        "",
        "_Flagged automatically: these items could not be verified against the "
        "repository files. Please check them before publishing._",
        "",
    ]
    lines += [f"- {issue.message}" for issue in issues]
    return base.rstrip() + "\n" + "\n".join(lines) + "\n"


if __name__ == "__main__":
    import argparse
    import sys

    from rich.console import Console

    from resurrect.fetch import open_repo
    from resurrect.scanner import scan

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Check generated docs against the repo.")
    parser.add_argument("docs", nargs="?", default="resurrected", help="folder of .md files")
    parser.add_argument("target", nargs="?", default=".", help="the repo the docs describe")
    parser.add_argument("--write", action="store_true", help="append a Needs review section")
    args = parser.parse_args()

    console = Console()
    with open_repo(args.target) as (folder, _name):
        repo_facts = scan(folder)
    for path in sorted(Path(args.docs).glob("*.md")):
        original = path.read_text(encoding="utf-8")
        found = verify_doc(original, repo_facts)
        console.print(f"[bold]{path.name}[/bold]: {len(found)} item(s) need review")
        for issue in found:
            console.print("  - " + issue.message, markup=False)
        if args.write:
            path.write_text(annotate_doc(original, found), encoding="utf-8")