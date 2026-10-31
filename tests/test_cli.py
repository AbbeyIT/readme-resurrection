from typer.testing import CliRunner
from resurrect.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Analyze a repository" in result.output