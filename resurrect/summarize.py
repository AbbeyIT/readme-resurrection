from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from resurrect.llm import LLMConfig, chat
from resurrect.scanner import LANGUAGES, TEST_DIRS, RepoFacts

PROMPT_VERSION = "2"
CACHE_DIR = ".resurrect-cache"
CACHE_FILE = "summaries.json"
SKIP_LANGUAGES = {"HTML", "CSS"}
MAX_FILE_BYTES = 500_000

SYSTEM_PROMPT = (
    "You are documenting a source code repository. You will be shown one file. "
    "Write a summary of 2 to 3 sentences describing what the file does, based only "
    "on the code shown. Name the main functions, classes, or exports. Do not guess "
    "about code you cannot see. If the file was shortened, say nothing about the "
    "omitted part. "
    "If the file ends with an `if __name__ == \"__main__\":` block, treat it as a demo and "
    "do not describe it as the purpose of the file. "
    "Reply with the summary only: no preamble and no headings."
)


def _is_test(rel: str) -> bool:
    parts = rel.lower().split("/")
    name = parts[-1]
    return (
        any(p in TEST_DIRS for p in parts[:-1])
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    )


def select_files(facts: RepoFacts, max_files: int = 12, min_bytes: int = 40) -> list[str]:
    """Choose the files worth summarizing: entry points first, then shallow, then large."""
    root = Path(facts.root)
    entry = set(facts.entry_points)
    ranked = []
    for rel in facts.tree:
        suffix = Path(rel).suffix.lower()
        language = LANGUAGES.get(suffix)
        if language is None or language in SKIP_LANGUAGES or _is_test(rel):
            continue
        try:
            size = (root / rel).stat().st_size
        except OSError:
            continue
        if size < min_bytes or size > MAX_FILE_BYTES:
            continue
        tier = 0 if rel in entry else 1
        ranked.append((tier, rel.count("/"), -size, rel))
    ranked.sort()
    return [item[3] for item in ranked[:max_files]]


def read_for_prompt(path: Path, max_chars: int = 3500) -> tuple[str, bool]:
    """Read a file, keeping the start and end if it is too long."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text, False
    head = text[: max_chars * 2 // 3]
    tail = text[-(max_chars // 3):]
    return head + "\n... [middle of file omitted] ...\n" + tail, True


def _cache_key(rel: str, content: str, model: str) -> str:
    raw = f"{PROMPT_VERSION}\0{model}\0{rel}\0{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cache(cache_path: Path) -> dict[str, str]:
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache_path: Path, cache: dict[str, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def summarize_repo(
    facts: RepoFacts,
    config: LLMConfig | None = None,
    max_files: int = 8,
    max_chars: int = 3500,
    cache_dir: str | Path | None = None,
    chat_fn: Callable = chat,
    on_progress: Callable[[int, int, str, bool], None] | None = None,
) -> dict[str, str]:
    """Return {relative_path: summary} for the most important files."""
    cfg = config or LLMConfig()
    root = Path(facts.root)
    cache_path = Path(cache_dir or CACHE_DIR) / CACHE_FILE
    cache = _load_cache(cache_path)

    files = select_files(facts, max_files=max_files)
    summaries: dict[str, str] = {}

    for done, rel in enumerate(files, start=1):
        content, _ = read_for_prompt(root / rel, max_chars=max_chars)
        key = _cache_key(rel, content, cfg.model)
        cached = key in cache
        if cached:
            summary = cache[key]
        else:
            prompt = f"File: {rel}\n\n```\n{content}\n```\n\nSummarize this file."
            summary = chat_fn(prompt, system=SYSTEM_PROMPT, config=cfg).strip()
            cache[key] = summary
            _save_cache(cache_path, cache)  # save as we go so an interrupted run keeps progress
        summaries[rel] = summary
        if on_progress:
            on_progress(done, len(files), rel, cached)
    return summaries


if __name__ == "__main__":
    import argparse

    from rich.console import Console
    from rich.progress import Progress

    from resurrect.fetch import open_repo
    from resurrect.llm import check_ollama
    from resurrect.scanner import scan

    parser = argparse.ArgumentParser(description="Summarize a repo's key files.")
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--max-files", type=int, default=12)
    parser.add_argument("--model", default=LLMConfig().model)
    args = parser.parse_args()

    console = Console()
    cfg = LLMConfig(model=args.model)
    check_ollama(cfg)
    with open_repo(args.target) as (folder, name):
        facts = scan(folder)
        with Progress(console=console) as progress:
            task = progress.add_task("Summarizing", total=None)

            def update(done, total, rel, cached):
                note = " (cached)" if cached else ""
                progress.update(task, total=total, completed=done, description=f"{rel}{note}")

            results = summarize_repo(facts, cfg, max_files=args.max_files, on_progress=update)
    for rel, summary in results.items():
        console.print(f"\n[bold]{rel}[/bold]")
        console.print(summary, markup=False)