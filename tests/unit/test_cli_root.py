from click.testing import CliRunner
from trader.cli.__main__ import cli

def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "broker" in result.output.lower()

def test_cli_unknown_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["nonexistent"])
    assert result.exit_code != 0
