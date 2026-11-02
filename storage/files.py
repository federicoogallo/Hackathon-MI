"""Read and replace the JSON data files without losing their records.

A data file that exists but cannot be parsed stops the caller: reading it as
empty would let the next save overwrite every record in it. Writes go to a
temporary file in the same folder, which then replaces the target in one
rename, so an interrupted save leaves the old file or the new one, never half.
"""

from __future__ import annotations

import contextlib
import base64
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


class CorruptDataFile(RuntimeError):
    """A data file exists but its content is not usable."""

    def __init__(self, path: Path, reason: str):
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"{self.path.name} non leggibile ({reason}): ripristinalo prima di una nuova scansione")


def read_json(path: Path, kind: type = dict) -> Any:
    """Parsed content of `path`; None when it is missing."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except ValueError as exc:  # invalid JSON, invalid UTF-8, empty or truncated file
        raise CorruptDataFile(path, f"JSON non valido: {exc}") from exc
    if not isinstance(data, kind):
        raise CorruptDataFile(path, f"atteso {kind.__name__}, trovato {type(data).__name__}")
    return data


def write_json(path: Path, payload: Any) -> Path:
    """Replace `path` with `payload` in one rename, keeping the file's permissions."""
    path = Path(path)
    content = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = 0o644
    _replace_bytes(path, content, mode)
    return path


def _replace_bytes(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def recover_publication(paths: list[Path], journal: Path) -> bool:
    """Restore both files after an interrupted publication; retain the journal on failure.

    Paths are supplied by the caller, never trusted from the on-disk journal.
    Recovery is repeatable if a second interruption happens while restoring.
    """
    saved = read_json(journal)
    if saved is None:
        return False
    expected = {str(Path(path).resolve()): Path(path).resolve() for path in paths}
    entries = saved.get("files")
    if saved.get("version") != 1 or not isinstance(entries, list) or len(entries) != len(expected):
        raise CorruptDataFile(journal, "registro di pubblicazione non valido")
    restored = {}
    for entry in entries:
        if (not isinstance(entry, dict) or not {"path", "content", "mode"} <= entry.keys()
                or not isinstance(entry.get("path"), str)):
            raise CorruptDataFile(journal, "voce di ripristino non valida")
        name = entry["path"]
        mode, content = entry.get("mode"), entry.get("content")
        if name not in expected or name in restored or type(mode) is not int or not 0 <= mode <= 0o777:
            raise CorruptDataFile(journal, "destinazione di ripristino non valida")
        try:
            if content is not None and not isinstance(content, str):
                raise ValueError()
            original = None if content is None else base64.b64decode(content, validate=True)
        except ValueError as exc:
            raise CorruptDataFile(journal, "contenuto di ripristino non valido") from exc
        restored[name] = (original, mode)
    # Validate the entire journal before touching either file.
    for name, (original, mode) in restored.items():
        path = expected[name]
        if original is None:
            path.unlink(missing_ok=True)
        else:
            _replace_bytes(path, original, mode)
    journal.unlink()
    return True


@contextlib.contextmanager
def publication_transaction(paths: list[Path], journal: Path):
    """Rollback a failed multi-file save and recover process interruptions next run.

    Writers must be serialized (the scheduled workflow already is). Individual
    replacements are atomic; readers may briefly see different generations.
    """
    paths = [Path(path).resolve() for path in paths]
    if len(set(paths)) != len(paths) or journal.resolve() in paths:
        raise ValueError("Le destinazioni della pubblicazione devono essere distinte")
    recover_publication(paths, journal)
    entries = []
    for path in paths:
        try:
            content = base64.b64encode(path.read_bytes()).decode("ascii")
            mode = stat.S_IMODE(path.stat().st_mode) & 0o777
        except FileNotFoundError:
            content, mode = None, 0o644
        entries.append({"path": str(path), "content": content, "mode": mode})
    _replace_bytes(journal, json.dumps({"version": 1, "files": entries}).encode("utf-8"), 0o600)
    try:
        yield
        # Removing the recovery record commits the pair.
        journal.unlink()
    except BaseException:
        recover_publication(paths, journal)
        raise
