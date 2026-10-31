from __future__ import annotations

from pathlib import Path
from typing import Callable

from resurrect.gitinfo import GitFacts
from resurrect.llm import LLMConfig, chat
from resurrect.scanner import RepoFacts

MAX_FACTS_CHARS = 8000  # about 2,000 tokens, leaving room for the reply in a 4096 context

RULES = (
    "Rules: 1) Use only the facts provided. "
    "2) If something is not in the facts, write 'unknown' or 'TODO: confirm' instead of guessing. "
    "3) Never invent commands, flags, URLs, package names, or features. "
    "Only use shell commands that appear in the VERIFIED COMMANDS list. "
    "4) Mention file paths from the facts where helpful. "
    "5) Never describe command-line arguments or options unless they appear in the facts. "
    "6) Output Markdown only, with no preamble and no closing remarks."
)

README_SYSTEM = (
    "You write README.md files for software repositories from facts supplied by the user. " + RULES
)

README_TASK = (
    "Write README.md with these sections: a '# ' title using the repository name; "
    "a short description of 2-3 sentences; '## Features' (bullets based on the file summaries); "
    "'## Installation'; "
    "'## Usage' (show only a command from the VERIFIED COMMANDS list or the command-line "
    "entry points, and suggest running it with --help; do not describe arguments or options); "
    "'## Project structure' (key folders and files); "
    "'## License' (state the license type only if the facts give one; if the type is not "
    "detected, name the license file and do not guess the type; if there is no license file, "
    "write 'unknown')."
)


def known_commands(facts: RepoFacts) -> list[str]:
    """Commands that are legitimate because the files that define them exist."""
    files = {Path(p).name for p in facts.dependency_files}
    cmds: list[str] = []
    if "requirements.txt" in files:
        cmds.append("pip install -r requirements.txt")
    if "pyproject.toml" in files or "setup.py" in files:
        cmds.append("pip install .")
    if "package.json" in files:
        cmds.append("npm install")
        cmds += [f"npm run {name}" for name in facts.scripts]
    if "go.mod" in files:
        cmds += ["go build ./...", "go test ./..."]
    if "Cargo.toml" in files:
        cmds += ["cargo build", "cargo test"]
    if "pom.xml" in files:
        cmds.append("mvn package")
    if "Gemfile" in files:
        cmds.append("bundle install")
    cmds += [f"{name} --help" for name in facts.cli_commands]
    cmds += [f"make {target}" for target in facts.make_targets]
    return list(dict.fromkeys(cmds))  # remove duplicates, keep order


def build_facts_block(
    facts: RepoFacts,
    git: GitFacts,
    summaries: dict[str, str],
    max_chars: int = MAX_FACTS_CHARS,
) -> str:
    lines = [f"Repository name: {facts.name}"]
    if git.is_repo and git.last_commit_date:
        lines.append(
            f"Last commit: {git.last_commit_date[:10]} ({git.days_since_last_commit} days ago)"
        )
        count = f"{git.total_commits}+" if git.is_shallow else str(git.total_commits)
        lines.append(f"Commits: {count}")
    lines.append(f"Files: {facts.file_count}")
    if facts.languages:
        lines.append("Languages (file counts): " + ", ".join(f"{k} {v}" for k, v in facts.languages.items()))
    lines.append("Dependency files: " + (", ".join(facts.dependency_files) or "none"))
    for rel, names in facts.dependencies.items():
        shown = ", ".join(names[:15]) + (" ..." if len(names) > 15 else "")
        lines.append(f"Dependencies in {rel}: {shown}")
    lines.append("Entry points: " + (", ".join(facts.entry_points) or "none found"))
    if facts.scripts:
        lines.append("package.json scripts: " + "; ".join(f"{k} = {v}" for k, v in facts.scripts.items()))
    if facts.make_targets:
        lines.append("Makefile targets: " + ", ".join(facts.make_targets))
    if facts.cli_commands:
        lines.append(
            "Command-line entry points (from pyproject.toml): "
            + ", ".join(f"{name} -> {target}" for name, target in facts.cli_commands.items())
        )
    lines.append("Test locations: " + (", ".join(facts.test_locations) or "none found"))
    if facts.license_file:
        kind = facts.license_type or "type not detected"
        lines.append(f"License file: {facts.license_file} (license type: {kind})")
    else:
        lines.append("License file: none")
    lines.append("Existing README: " + (facts.readme_file or "none"))

    top = sorted({p.split("/")[0] + ("/" if "/" in p else "") for p in facts.tree})[:40]
    lines.append("Top-level contents: " + ", ".join(top))

    commands = known_commands(facts)
    lines.append(
        "VERIFIED COMMANDS (run in the folder containing the matching file): "
        + (" | ".join(commands) if commands else "none")
    )

    block = "\n".join(lines)
    header = "\n\nFILE SUMMARIES:\n"
    out = block + header
    for rel, summary in summaries.items():
        entry = f"- {rel}: {summary}\n"
        if len(out) + len(entry) > max_chars:
            break
        out += entry
    return out.rstrip()


def clean_output(text: str) -> str:
    """Strip a code fence the model sometimes wraps around the whole document."""
    text = text.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else ""
        stripped = text.rstrip()
        if stripped.endswith("```"):
            text = stripped[:-3]
    return text.strip() + "\n"


def generate_readme(
    facts: RepoFacts,
    git: GitFacts,
    summaries: dict[str, str],
    config: LLMConfig | None = None,
    chat_fn: Callable = chat,
    on_token: Callable[[str], None] | None = None,
) -> str:
    block = build_facts_block(facts, git, summaries)
    prompt = f"{block}\n\n{README_TASK}"
    raw = chat_fn(
        prompt,
        system=README_SYSTEM,
        config=config,
        stream=on_token is not None,
        on_token=on_token,
    )
    return clean_output(raw)


def write_doc(out_dir: str | Path, filename: str, text: str) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(text, encoding="utf-8")
    return path


if __name__ == "__main__":
    import argparse
    import sys

    from rich.console import Console

    from resurrect.fetch import open_repo
    from resurrect.gitinfo import get_git_facts
    from resurrect.llm import check_ollama
    from resurrect.scanner import scan
    from resurrect.summarize import summarize_repo

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Generate README.md for a repo.")
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--out", default="resurrected")
    parser.add_argument("--max-files", type=int, default=8)
    parser.add_argument("--model", default=LLMConfig().model)
    args = parser.parse_args()

    console = Console()
    cfg = LLMConfig(model=args.model)
    check_ollama(cfg)
    with open_repo(args.target) as (folder, name):
        repo_facts = scan(folder)
        git_facts = get_git_facts(folder)
        console.print("Summarizing key files (cached results load instantly)...")
        file_summaries = summarize_repo(repo_facts, cfg, max_files=args.max_files)
        console.print("Writing README.md...\n")
        text = generate_readme(
            repo_facts, git_facts, file_summaries, cfg,
            on_token=lambda t: print(t, end="", flush=True),
        )
    path = write_doc(args.out, "README.md", text)
    console.print(f"\n\nSaved to {path}")