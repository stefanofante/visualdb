"""dbvisual entrypoint.

Run the monolithic NiceGUI application in desktop (native window) or web mode:

    python main.py --mode desktop     # default: native window
    python main.py --mode web         # browser UI on 127.0.0.1:8080

NiceGUI's native/reload machinery re-imports this module in a child process, so
the launch logic lives under an ``__main__`` / ``__mp_main__`` guard and
``multiprocessing.freeze_support()`` is called for frozen (packaged) builds.
"""

from dbvisual.app.cli import main

if __name__ in {"__main__", "__mp_main__"}:
    main()
