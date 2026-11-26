"""Start the frozen app and request real UI routes before wrapping the installer."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

BINARIES = {
    "darwin": "DBVisual.app/Contents/MacOS/DBVisual",
    "win32": "DBVisual/DBVisual.exe",
    "linux": "DBVisual/DBVisual",
}


def main() -> None:
    executable = Path(__file__).resolve().parents[1] / "dist" / BINARIES[sys.platform]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, BROWSER="echo")
    with subprocess.Popen(
        [str(executable), "--mode", "web", "--port", str(port)], env=env
    ) as child:
        try:
            for route in ("/", "/connections", "/help"):
                deadline = time.monotonic() + 60
                while True:
                    if child.poll() is not None:
                        raise RuntimeError(
                            f"Frozen app exited with status {child.returncode}."
                        )
                    try:
                        with urlopen(
                            f"http://127.0.0.1:{port}{route}", timeout=5
                        ) as response:
                            if b"nicegui" not in response.read().lower():
                                raise RuntimeError(f"Unexpected response for {route}")
                        break
                    except URLError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.25)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()


if __name__ == "__main__":
    main()
