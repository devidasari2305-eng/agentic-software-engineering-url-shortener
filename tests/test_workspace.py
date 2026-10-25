import pytest

from orchestrator.errors import PolicyViolation
from orchestrator.workspace import Workspace


def test_write_read_delete_and_manifest(tmp_path):
    ws = Workspace(tmp_path / "w")
    assert ws.write("src/a.py", "x = 1\n") == "src/a.py"
    assert ws.read("src/a.py") == "x = 1\n"
    first = ws.manifest()["src/a.py"]
    ws.write("src/a.py", "x = 2\n")
    assert ws.manifest()["src/a.py"] != first
    ws.delete("src/a.py")
    assert not ws.exists("src/a.py")
    assert not (ws.root / "src").exists()  # empty parent directories are pruned


@pytest.mark.parametrize("path", ["../escape.txt", "a/../../escape.txt", ".checkpoints/x"])
def test_path_traversal_and_checkpoint_writes_are_blocked(tmp_path, path):
    ws = Workspace(tmp_path / "w")
    with pytest.raises(PolicyViolation) as error:
        ws.write(path, "boom")
    assert error.value.rule_id == "POL-006"
    assert not (tmp_path / "escape.txt").exists()


def test_restore_returns_workspace_to_checkpoint(tmp_path):
    ws = Workspace(tmp_path / "w")
    ws.write("keep.txt", "original")
    ws.snapshot("cp1")
    ws.write("keep.txt", "modified")
    ws.write("new/added.txt", "extra")
    ws.restore("cp1")
    assert ws.read("keep.txt") == "original"
    assert ws.files() == ["keep.txt"]


def test_restore_unknown_checkpoint_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        Workspace(tmp_path / "w").restore("missing")
