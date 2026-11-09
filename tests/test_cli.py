"""Tests for the initial command-line interface."""

from swing_trading_research.cli import main


def test_cli_without_command_shows_help(capsys) -> None:
    assert main([]) == 0

    output = capsys.readouterr().out
    assert "swing-research" in output
    assert "US and UK" in output


def test_version_command(capsys) -> None:
    assert main(["version"]) == 0

    assert capsys.readouterr().out.strip() == "0.1.0"
