"""Tests for CLI module."""

import pytest
from typer.testing import CliRunner
from app.cli import app

runner = CliRunner()


class TestCLI:
    """Test CLI commands."""

    def test_config_command(self):
        """Test config command."""
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "Download Directory" in result.output

    def test_help_command(self):
        """Test help command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Video Finder" in result.output
