"""Sandboxed per-workflow workspace with path-traversal protection, hashing and checkpoints."""

import hashlib
import shutil
from pathlib import Path

from orchestrator.errors import PolicyViolation

CHECKPOINT_DIR = ".checkpoints"
_IGNORED_PARTS = {CHECKPOINT_DIR, "__pycache__", ".pytest_cache"}


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PolicyViolation("POL-006", f"Path escapes the workflow workspace: {relative}")
        if CHECKPOINT_DIR in candidate.relative_to(self.root).parts:
            raise PolicyViolation("POL-006", "Agents may not write to checkpoint storage")
        return candidate

    def write(self, relative: str, content: str) -> str:
        path = self._resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        return path.relative_to(self.root).as_posix()

    def read(self, relative: str) -> str:
        return self._resolve(relative).read_text(encoding="utf-8")

    def exists(self, relative: str) -> bool:
        return self._resolve(relative).is_file()

    def delete(self, relative: str) -> None:
        path = self._resolve(relative)
        if path.is_file():
            path.unlink()
        parent = path.parent
        while parent != self.root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent

    def files(self) -> list[str]:
        found = []
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root)
            if path.is_file() and not (set(relative.parts) & _IGNORED_PARTS):
                found.append(relative.as_posix())
        return found

    def manifest(self) -> dict[str, str]:
        return {f: hashlib.sha256((self.root / f).read_bytes()).hexdigest() for f in self.files()}

    def snapshot(self, label: str) -> dict:
        target = self.root / CHECKPOINT_DIR / label
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        manifest = self.manifest()
        for relative in manifest:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / relative, destination)
        return {
            "label": label,
            "files": len(manifest),
            "manifest_sha256": hashlib.sha256(
                "".join(f"{k}:{v}" for k, v in sorted(manifest.items())).encode()
            ).hexdigest(),
        }

    def restore(self, label: str) -> None:
        source = self.root / CHECKPOINT_DIR / label
        if not source.is_dir():
            raise FileNotFoundError(f"Checkpoint not found: {label}")
        for entry in list(self.root.iterdir()):
            if entry.name == CHECKPOINT_DIR:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        for path in source.rglob("*"):
            if path.is_file():
                destination = self.root / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
