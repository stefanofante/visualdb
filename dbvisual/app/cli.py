"""Console-script entrypoint (``dbvisual`` command).

Mirrors the top-level ``main.py`` launcher so the app can be started either with
``python main.py`` or via the installed ``dbvisual`` command.
"""

from __future__ import annotations

import argparse
import multiprocessing

from dbvisual.app.app_settings import get_startup_mode


def main() -> None:
    """Parse CLI arguments and launch the app."""
    multiprocessing.freeze_support()
    from dbvisual.app.main import run

    parser = argparse.ArgumentParser(
        prog="dbvisual", description="Local visual DB builder"
    )
    parser.add_argument(
        "--mode",
        choices=["desktop", "web"],
        default=get_startup_mode(),
        help="Launch as a native desktop window (default) or a local web app.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web mode bind host.")
    parser.add_argument("--port", type=int, default=8080, help="Web mode port.")
    args = parser.parse_args()
    run(mode=args.mode, host=args.host, port=args.port)


if __name__ in {"__main__", "__mp_main__"}:
    main()
