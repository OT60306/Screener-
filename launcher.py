"""
Desktop-launcher entry point for the PyInstaller .exe build. Starts the
Streamlit server in-process (via streamlit.web.bootstrap, the same call
`streamlit run` itself makes) pointed at Home.py, and opens the default
browser once the server is accepting connections. Not used by
`streamlit run Home.py` directly — that keeps working exactly as before for
normal dev use; this file only matters for the packaged .exe.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser


def _resource_path(relative_path: str) -> str:
    """Resolves a path both when run as a normal script (dev) and when
    frozen into a PyInstaller onefile .exe (files unpacked to sys._MEIPASS
    at runtime)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def _find_free_port(preferred: int = 8501) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def _open_browser_when_ready(url: str, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.3)
    webbrowser.open(url)  # give up waiting, try anyway


PORT = _find_free_port()

if __name__ == "__main__":
    # Run from the unpacked bundle directory so relative paths in the app
    # (config.yaml, data/, .streamlit/) resolve correctly.
    os.chdir(_resource_path("."))

    from streamlit.web import bootstrap

    url = f"http://localhost:{PORT}"
    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()

    print(f"Starting Stock Intel & Health Scorecard at {url} ...")
    print("Close this window to stop the app.")

    sys.argv = ["streamlit", "run", _resource_path("Home.py")]
    flag_options = {
        "server.port": PORT,
        "server.headless": True,
        "server.fileWatcherType": "none",  # avoid watchdog issues watching files inside the frozen temp dir
        "global.developmentMode": False,
    }
    bootstrap.load_config_options(flag_options=flag_options)
    bootstrap.run(_resource_path("Home.py"), False, [], flag_options)
