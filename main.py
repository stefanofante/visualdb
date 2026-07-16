"""dbvisual entrypoint.

Run the monolithic NiceGUI application in desktop (native window) or web mode:

    python main.py --mode desktop     # default: native window
    python main.py --mode web         # browser UI on 127.0.0.1:8080

NiceGUI's native/reload machinery re-imports this module in a child process, so
the launch logic lives under an ``__main__`` / ``__mp_main__`` guard and
``multiprocessing.freeze_support()`` is called for frozen (packaged) builds.
"""

from __future__ import annotations

import argparse
import multiprocessing

from dbvisual.app.main import run


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dbvisual", description="Local visual DB builder"
    )
    parser.add_argument(
        "--mode",
        choices=["desktop", "web"],
        default="desktop",
        help="Launch as a native desktop window (default) or a local web app.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web mode bind host.")
    parser.add_argument("--port", type=int, default=8080, help="Web mode port.")
    return parser.parse_args()


if __name__ in {"__main__", "__mp_main__"}:
    multiprocessing.freeze_support()
    _args = _parse_args()
    run(mode=_args.mode, host=_args.host, port=_args.port)
