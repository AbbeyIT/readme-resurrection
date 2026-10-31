from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

REMOTE_PREFIXES = ("http://", "https://", "git@", "ssh://", "file://")


class CloneError(RuntimeError):
    """Raised when a repository cannot be cloned."""


def is_remote(target: str) -> bool:
    return target.strip().lower().startswith(REMOTE_PREFIXES)


def normalize_url(url: str) -> str:
    """Reduce github.com/owner/repo/tree/main/... style links to the repo URL."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.netloc.lower() in ("github.com", "www.github.com"):
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
            return f"https://github.com/{parts[0]}/{repo}"
    return url.rstrip("/")


def repo_name_from_url(url: str) -> str:
    tail = url.rstrip("/").replace("\\", "/").split("/")[-1]
    tail = tail.split(":")[-1]  # handles git@host:owner/repo.git
    if tail.endswith(".git"):
        tail = tail[:-4]
    return tail or "repo"


def _force_remove(func, path, _exc) -> None:
    """Windows keeps .git objects read-only; clear the flag and retry."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _rmtree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_remove)
    else:
        shutil.rmtree(path, onerror=_force_remove)


def clone_repo(url: str, dest: Path, depth: int = 50) -> None:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # fail instead of asking for a password
    cmd = ["git", "clone", "--depth", str(depth), "--quiet", url, str(dest)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300, env=env,
        )
    except FileNotFoundError as exc:
        raise CloneError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise CloneError("git clone timed out after 5 minutes") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or "unknown error"
        raise CloneError(f"Could not clone {url}: {message}")


@contextmanager
def open_repo(target: str) -> Iterator[tuple[Path, str]]:
    """Yield (folder, display_name). Remote URLs are cloned to a temp folder
    that is deleted when the block ends. Local paths are used in place."""
    if not is_remote(target):
        path = Path(target).expanduser().resolve()
        if not path.is_dir():
            raise CloneError(f"Not a folder: {path}")
        yield path, path.name
        return

    url = normalize_url(target)
    name = repo_name_from_url(url)
    tmp_root = Path(tempfile.mkdtemp(prefix="resurrect-"))
    dest = tmp_root / name
    try:
        clone_repo(url, dest)
        yield dest, name
    finally:
        _rmtree(tmp_root)


if __name__ == "__main__":
    from resurrect.gitinfo import get_git_facts
    from resurrect.scanner import scan

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    with open_repo(target) as (folder, name):
        facts = scan(folder)
        git = get_git_facts(folder)
        print(f"Name: {name}")
        print(f"Files: {facts.file_count}")
        print(f"Languages: {facts.languages}")
        print(f"Dependency files: {facts.dependency_files}")
        print(f"Entry points: {facts.entry_points}")
        print(f"README: {facts.readme_file}  License: {facts.license_file}")
        print(f"Last commit: {git.last_commit_date}  Shallow: {git.is_shallow}")
        print(f"Days since last commit: {git.days_since_last_commit}")
    print("Temp folder cleaned up:", not folder.exists())