"""Public commands accept user-supplied work and cannot generate example cases."""

from pathlib import Path

import pytest

from omphalos.cli import parser


def test_removed_demo_command_is_rejected_before_creating_a_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = tmp_path / "workspace"
    with pytest.raises(SystemExit) as stopped:
        parser().parse_args(["--workspace", str(workspace), "demo"])
    assert stopped.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert not workspace.exists()
