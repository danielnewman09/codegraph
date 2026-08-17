"""Regression checks for the retired static HTML export surface."""

from __future__ import annotations

import importlib
import sys

import pytest


def test_public_packages_import_without_html_export() -> None:
    codegraph = importlib.import_module("codegraph")
    export = importlib.import_module("codegraph.export")

    assert not hasattr(codegraph, "export_html")
    assert not hasattr(export, "export_html")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("codegraph.export.viz")


def test_python_module_help_lists_only_retained_commands(monkeypatch, capsys) -> None:
    from codegraph import __main__

    monkeypatch.setattr(sys, "argv", ["python -m codegraph", "--help"])
    with pytest.raises(SystemExit) as exc:
        __main__.main()

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "db" in output
    assert "viz" not in output


def test_python_module_rejects_retired_command(monkeypatch, capsys) -> None:
    from codegraph import __main__

    monkeypatch.setattr(sys, "argv", ["python -m codegraph", "viz"])
    with pytest.raises(SystemExit) as exc:
        __main__.main()

    assert exc.value.code == 1
    assert "Unknown subcommand: viz" in capsys.readouterr().err
