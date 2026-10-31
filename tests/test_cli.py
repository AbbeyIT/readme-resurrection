import pytest
from typer.testing import CliRunner

from resurrect.cli import app
from resurrect.llm import LLMError

runner = CliRunner()


def make_repo(tmp_path):
    repo = tmp_path / "ghostrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hello')\n" * 5)
    return repo


@pytest.fixture
def fake_pipeline(monkeypatch):
    monkeypatch.setattr("resurrect.cli.check_ollama", lambda cfg: None)
    monkeypatch.setattr(
        "resurrect.cli.summarize_repo",
        lambda facts, cfg, max_files=8, on_progress=None: {},
    )
    monkeypatch.setattr(
        "resurrect.cli.generate_doc",
        lambda kind, facts, git, summaries, config=None, on_token=None: (
            f"# {kind}\n\nRun `npm install`.\n"
        ),
    )


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Analyze a repository" in result.output


def test_dry_run_prints_report_without_ollama(tmp_path):
    result = runner.invoke(app, [str(make_repo(tmp_path)), "--dry-run"])
    assert result.exit_code == 0
    assert "Resurrection report" in result.output
    assert "ghostrepo" in result.output
    assert "Dry run" in result.output


def test_unknown_skip_is_rejected(tmp_path):
    result = runner.invoke(app, [str(make_repo(tmp_path)), "--skip", "bogus", "--dry-run"])
    assert result.exit_code != 0


def test_missing_folder_fails_cleanly(tmp_path):
    result = runner.invoke(app, [str(tmp_path / "nope"), "--dry-run"])
    assert result.exit_code == 1
    assert "Not a folder" in result.output


def test_full_run_writes_docs_and_flags_bad_claims(tmp_path, fake_pipeline):
    out = tmp_path / "out"
    result = runner.invoke(
        app, [str(make_repo(tmp_path)), "--out", str(out), "--skip", "architecture"]
    )
    assert result.exit_code == 0, result.output
    for name in ("README.md", "SETUP.md", "CONTRIBUTING.md"):
        assert (out / name).exists()
    assert not (out / "ARCHITECTURE.md").exists()
    text = (out / "README.md").read_text(encoding="utf-8")
    assert "## Needs review" in text
    assert "npm install" in text


def test_no_verify_skips_review_section(tmp_path, fake_pipeline):
    out = tmp_path / "out"
    result = runner.invoke(app, [str(make_repo(tmp_path)), "--out", str(out), "--no-verify"])
    assert result.exit_code == 0, result.output
    assert "Needs review" not in (out / "README.md").read_text(encoding="utf-8")


def test_model_error_exits_cleanly(tmp_path, monkeypatch, fake_pipeline):
    def boom(*args, **kwargs):
        raise LLMError("the model fell over")

    monkeypatch.setattr("resurrect.cli.generate_doc", boom)
    result = runner.invoke(app, [str(make_repo(tmp_path)), "--out", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "the model fell over" in result.output


def test_everything_skipped(tmp_path):
    args = [str(make_repo(tmp_path))]
    for kind in ("readme", "setup", "architecture", "contributing"):
        args += ["--skip", kind]
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    assert "nothing to generate" in result.output