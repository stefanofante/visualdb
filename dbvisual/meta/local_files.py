"""Replace user settings and encrypted data without exposing a partial write."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def atomic_write(path: Path, data: bytes) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
