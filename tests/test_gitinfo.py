import os
import subprocess

from resurrect.gitinfo import get_git_facts

IDENTITY = {
    "GIT_AUTHOR_NAME": "Zeus",
    "GIT_AUTHOR_EMAIL": "zeus@example.com",
    "GIT_COMMITTER_NAME": "Zeus",
    "GIT_COMMITTER_EMAIL": "zeus@example.com",
}


def git(cwd, *args, date=None):
    env = {**os.environ, **IDENTITY}
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def test_not_a_repo(tmp_path):
    facts = get_git_facts(tmp_path)
    assert facts.is_repo is False
    assert facts.total_commits == 0
    assert facts.days_since_last_commit is None


def test_empty_repo(tmp_path):
    git(tmp_path, "init")
    facts = get_git_facts(tmp_path)
    assert facts.is_repo is True
    assert facts.last_commit_date is None


def test_repo_with_history(tmp_path):
    git(tmp_path, "init")
    (tmp_path / "a.txt").write_text("one")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "first", date="2020-01-01T12:00:00+00:00")
    (tmp_path / "a.txt").write_text("two")
    git(tmp_path, "commit", "-am", "second", date="2020-06-01T12:00:00+00:00")

    facts = get_git_facts(tmp_path)
    assert facts.is_repo is True
    assert facts.total_commits == 2
    assert facts.last_commit_message == "second"
    assert facts.first_commit_date.startswith("2020-01-01")
    assert facts.last_commit_date.startswith("2020-06-01")
    assert facts.top_contributors == ["Zeus"]
    assert facts.days_since_last_commit >= 1000
    assert facts.is_shallow is False