import os
import subprocess

import pytest

from resurrect.fetch import (
    CloneError, is_remote, normalize_url, open_repo, repo_name_from_url,
)

IDENTITY = {
    "GIT_AUTHOR_NAME": "Zeus", "GIT_AUTHOR_EMAIL": "zeus@example.com",
    "GIT_COMMITTER_NAME": "Zeus", "GIT_COMMITTER_EMAIL": "zeus@example.com",
}


def test_is_remote():
    assert is_remote("https://github.com/a/b")
    assert is_remote("git@github.com:a/b.git")
    assert not is_remote(r"D:\Projects\thing")
    assert not is_remote(".")


def test_normalize_url():
    assert normalize_url("https://github.com/a/b/tree/main/src") == "https://github.com/a/b"
    assert normalize_url("https://github.com/a/b.git") == "https://github.com/a/b"
    assert normalize_url("https://github.com/a/b/") == "https://github.com/a/b"


def test_repo_name_from_url():
    assert repo_name_from_url("https://github.com/a/b") == "b"
    assert repo_name_from_url("git@github.com:a/b.git") == "b"


def test_open_repo_local_path(tmp_path):
    with open_repo(str(tmp_path)) as (folder, name):
        assert folder == tmp_path.resolve()
        assert name == tmp_path.name
    assert tmp_path.exists()  # local folders are never deleted


def test_open_repo_missing_folder(tmp_path):
    with pytest.raises(CloneError):
        with open_repo(str(tmp_path / "nope")):
            pass


def test_open_repo_clones_and_cleans_up(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    env = {**os.environ, **IDENTITY}
    (source / "hello.txt").write_text("hi")
    for args in (["init"], ["add", "."], ["commit", "-m", "init"]):
        subprocess.run(["git", *args], cwd=source, env=env, check=True, capture_output=True)

    with open_repo(source.as_uri()) as (folder, name):
        assert name == "source"
        assert (folder / "hello.txt").exists()
        saved = folder
    assert not saved.exists()  # temp clone was removed
    assert source.exists()


def test_clone_failure_raises(tmp_path):
    with pytest.raises(CloneError):
        with open_repo((tmp_path / "missing").as_uri()):
            pass