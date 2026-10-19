"""Desktop entry point for Job Finder.

Boots the existing FastAPI app on a local port inside this process, then shows
it in a native OS window via pywebview. Also runs a GitHub-Releases update
check shortly after launch and offers a one-click update.

Run in dev:   python desktop/launcher.py
When frozen:  this module is the PyInstaller entry script.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import os
import socket
import sys
import threading
import time

# --- Make the project importable and set writable paths BEFORE importing app #
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

def _ensure_std_streams() -> None:
    """Give the process real stdout/stderr objects.

    Launched through `pythonw.exe` (which is what the Windows shortcut uses so
    no console window appears) Python sets `sys.stdout` and `sys.stderr` to
    None. Any library that touches them then dies - uvicorn's log formatter
    calls `sys.stdout.isatty()` and the whole app failed to start with
    "ValueError: Unable to configure formatter 'default'". Pointing the streams
    at os.devnull costs nothing and removes the entire class of failure."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            except OSError:
                pass


_ensure_std_streams()

try:
    from paths import is_frozen, user_data_dir  # noqa: E402
except Exception as _exc:  # noqa: BLE001 - nothing is set up yet, not even logging
    # A broken install (missing/renamed app files) would otherwise vanish
    # without a trace when started from a pythonw.exe shortcut.
    if sys.platform.startswith("win"):
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, f"Job Finder install looks incomplete:\n\n{_exc}\n\n"
                  f"Expected the app files next to:\n{_HERE}",
            "Job Finder could not start", 0x10)
    raise

class _SecretsFilter:
    """Keeps credentials out of the log file.

    httpx logs every request as its full URL, and Telegram puts the bot token in
    the path - so a working digest wrote the token into `jobfinder.log` on every
    send, in plain text, in a file people attach to bug reports. The log is not
    a place to store a credential, and the token is not needed to read it."""

    _PATTERNS = (
        # https://api.telegram.org/bot<token>/sendMessage
        re.compile(r"(/bot)[0-9]+:[A-Za-z0-9_\-]{20,}"),
        # Bearer / key= style, in case a provider ever logs one.
        re.compile(r"\b(sk-)[A-Za-z0-9_\-]{16,}"),
        # Google (Gemini) keys: "AIza" + 35 characters. The OpenAI-compatible
        # endpoint takes it in a header, but Google's own REST API puts it in
        # the URL as ?key=, which httpx would log whole.
        re.compile(r"\b(AIza)[0-9A-Za-z_\-]{30,}"),
        re.compile(r"(?i)\b(api[_-]?key=)[^&\s\"']+"),
    )

    class Formatter(logging.Formatter):
        def format(self, record):
            text = super().format(record)
            for pattern in _SecretsFilter._PATTERNS:
                text = pattern.sub(r"\1<redacted>", text)
            return text


def _setup_logging():
    """Log to BOTH the console (dev) and a file in the user data dir, so the
    logs are visible even when the app is launched by double-clicking the .app
    (no terminal attached)."""
    fmt = _SecretsFilter.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if sys.stderr is not None:          # None under pythonw.exe before the fix above
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    try:
        log_path = user_data_dir() / "jobfinder.log"
        # Rotating, not endless. A month of ordinary use produced 21 MB, and a
        # log nobody can open is a log nobody reads. Five files of five megabytes
        # keeps roughly the last fortnight, and the rotation eventually retires
        # the older file that still holds secrets written before redaction
        # existed.
        fileh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8")
        fileh.setFormatter(fmt)
        root.addHandler(fileh)
        root.info("Logging to %s", log_path)
    except Exception as exc:  # noqa: BLE001
        root.warning("Could not open log file: %s", exc)


class _LastError(logging.Handler):
    """Remember the most recent ERROR record.

    When the FastAPI lifespan raises, uvicorn logs the traceback and shuts down
    *cleanly* - no exception reaches this process, so the launcher could only
    report a useless "did not start within 20 seconds". Keeping the last error
    lets the dialog name the real cause instead (this is how the Windows tzdata
    crash stayed invisible for a release)."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.text: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.text = record.getMessage().strip().splitlines()[-1][:300]
        except Exception:  # noqa: BLE001 - a logging handler must never raise
            pass


_setup_logging()
_last_error = _LastError()
logging.getLogger().addHandler(_last_error)
logger = logging.getLogger("jobfinder.launcher")


def _ensure_dyld():
    """Make the bundled native libs (pango/cairo for WeasyPrint) discoverable.

    They live in Contents/Frameworks (== sys._MEIPASS for a onedir .app). dyld
    reads DYLD_* only at process start, so if it isn't set yet we set it and
    re-exec once. (Note: DYLD_* injection is blocked under a hardened runtime /
    notarized build - see desktop/README.md.)
    """
    if sys.platform != "darwin" or not is_frozen():
        return   # macOS-only trick (Windows/Linux don't use DYLD_*)
    if os.environ.get("JF_DYLD_READY") == "1":
        return
    fw = getattr(sys, "_MEIPASS", "")
    os.environ["JF_DYLD_READY"] = "1"
    if fw:
        prev = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = fw + ((":" + prev) if prev else "")
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv[1:])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not re-exec for dylib path: %s", exc)


def _message_box(title: str, message: str) -> None:
    """Show a native dialog. Launched from a shortcut with pythonw.exe there is
    no console, so without this a startup crash is completely invisible - the
    app just doesn't appear (exactly what Windows users reported)."""
    try:
        if sys.platform.startswith("win"):
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)  # MB_ICONERROR
        elif sys.platform == "darwin":
            import subprocess

            subprocess.run(
                ["osascript", "-e",
                 f'display alert "{title}" message "{message}" as critical'],
                check=False,
            )
    except Exception:  # noqa: BLE001 - a failed dialog must not mask the error
        pass


def _fatal(exc: BaseException) -> None:
    """Log the traceback, tell the user where the log is, and exit non-zero."""
    import traceback

    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Job Finder failed to start:\n%s", detail)
    try:
        log_path = str(user_data_dir() / "jobfinder.log")
    except Exception:  # noqa: BLE001
        log_path = "(log unavailable)"
    _message_box(
        "Job Finder could not start",
        f"{type(exc).__name__}: {exc}\n\nFull details: {log_path}",
    )
    sys.exit(1)


def _enable_context_menu() -> None:
    """Restore the right-click menu (Copy / Select All / Look Up) on macOS.

    pywebview's Cocoa backend wipes every item from the native context menu
    unless it is running in debug mode:

        def willOpenMenu_withEvent_(self, menu, event):
            if not _state['debug']:
                menu.removeAllItems()

    The result is a desktop app where right-click → Copy simply does not exist,
    which reads as "copying is disabled". ⌘C keeps working (pywebview does add
    an Edit menu), but right-click is what people reach for. Neutralising that
    one method gives the standard WKWebView menu back without turning on debug
    mode and its dev tools."""
    if sys.platform != "darwin":
        return
    try:
        from webview.platforms.cocoa import BrowserView

        BrowserView.WebKitHost.willOpenMenu_withEvent_ = (
            lambda self, menu, event: None  # keep whatever WKWebView offers
        )
        logger.info("Native context menu enabled (copy/select all).")
    except Exception as exc:  # noqa: BLE001 - cosmetic, never block startup
        logger.info("Could not enable the context menu: %s", exc)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _preferred_port() -> int:
    """Prefer a STABLE port so the Chrome extension can POST to /api/ingest at a
    known address (default 8000, override with JF_PORT). Fall back to a random
    free port only if it's already taken."""
    try:
        want = int(os.environ.get("JF_PORT", "8000") or 8000)
    except ValueError:
        want = 8000
    # Walk a SMALL, PREDICTABLE range. The Chrome extension has to find this
    # server on its own, and a random high port made it invisible: scans ran,
    # posted to :8000, and the jobs vanished because the app had quietly moved.
    # The extension probes 8000-8010, so stay inside that window.
    for port in range(want, want + 11) if want > 0 else ():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            if port != want:
                logger.warning("Port %d was busy — serving on %d instead. The "
                               "extension probes 8000-8010, so it will still "
                               "find the app.", want, port)
            return port
        except OSError:
            continue
        finally:
            sock.close()
    logger.warning("Ports %d-%d are all busy — using a random one. The Chrome "
                   "extension will NOT find the app.", want, want + 10)
    return _free_port()


def _wait_until_up(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


# Set when the server thread dies, so the main thread can report the REAL
# reason instead of a bare "did not start in time".
_server_error: BaseException | None = None


def _start_server(port: int):
    import uvicorn
    from main import app  # imported AFTER env is configured

    # log_config=None: keep the logging set up in _setup_logging() and stop
    # uvicorn from running its own dictConfig, whose colour-aware formatter is
    # what broke the Windows launch. Belt and braces with _ensure_std_streams().
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info",
                            log_config=None)
    server = uvicorn.Server(config)

    def _serve():
        global _server_error
        try:
            server.run()
        except BaseException as exc:  # noqa: BLE001 - otherwise lost to a dead thread
            _server_error = exc
            logger.exception("Server thread crashed: %s", exc)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return server


def _updater():
    try:
        from desktop import updater
    except Exception:
        import updater  # type: ignore
    return updater


def _alert(window, message: str):
    try:
        window.evaluate_js("window.alert(%r)" % message)
    except Exception:
        logger.info(message)


def _run_update_flow(window, silent: bool):
    """Check GitHub and, if newer, offer a one-click update.
    silent=True (startup): stay quiet when already up to date.
    silent=False (menu):   tell the user either way."""
    updater = _updater()
    try:
        info = updater.update_available()
    except Exception as exc:  # noqa: BLE001
        logger.info("Update check failed: %s", exc)
        if not silent:
            _alert(window, "Couldn't check for updates right now.")
        return
    if not info:
        if not silent:
            _alert(window, "You're up to date (v%s)." % updater.__version__)
        return
    logger.info("Update available: %s", info["version"])
    msg = (f"Job Finder {info['version']} is available "
           f"(you have {updater.__version__}). Update now?")
    approved = False
    try:
        approved = bool(window.create_confirmation_dialog("Update available", msg))
    except Exception:
        import webbrowser
        webbrowser.open(f"https://github.com/{updater.GITHUB_REPO}/releases/latest")
        return
    if approved:
        if updater.download_and_apply(info["url"]):
            os._exit(0)          # hand-off script relaunches the new build
        elif not silent:
            _alert(window, "Update failed to download. Try again later.")


def main():
    _ensure_dyld()   # may re-exec once (frozen only) so bundled dylibs load

    # Writable DB location (the .app bundle is read-only).
    os.environ.setdefault("DB_PATH", str(user_data_dir() / "jobs.db"))
    # Desktop default: no fixed-interval scheduler; the user schedules scans in
    # Settings. (They can still hit "Scan now".)
    os.environ.setdefault("SCRAPE_INTERVAL_MINUTES", "0")

    port = _preferred_port()
    # Publish it: the Telegram digest links back into the app, and the app can
    # land on a different port than the .env default.
    os.environ["JOBFINDER_RUNTIME_PORT"] = str(port)
    os.environ["PORT"] = str(port)

    logger.info("Starting Job Finder on %s/%s, 127.0.0.1:%d (data: %s)",
                sys.platform, sys.version.split()[0], port, user_data_dir())
    _start_server(port)
    if not _wait_until_up(port):
        if _server_error is not None:
            raise _server_error
        if _last_error.text:
            # uvicorn exited cleanly after a failed startup: the traceback only
            # went to the log, so surface its last line in the dialog.
            raise RuntimeError(f"The app failed during startup: {_last_error.text}")
        raise RuntimeError(
            "The local server did not start within 20 seconds — see the log for "
            "the underlying error."
        )

    try:
        import webview  # imported late so the server can start first

        _enable_context_menu()
    except Exception as exc:  # noqa: BLE001 - no native window available
        logger.warning("pywebview unavailable (%s) — falling back to the browser.", exc)
        _run_in_browser(port)
        return

    # text_select=True, because pywebview's default is False and that is not a
    # cosmetic default: it injects
    #     body { user-select: none; cursor: default; }
    # into the page, so nothing in the whole app can be selected and the text
    # cursor never appears. Every score, summary, company name and generated
    # letter was unselectable - in an app whose output exists to be pasted into
    # somebody else's form. Restoring the native context menu (above) only gave
    # back a Copy item that had nothing to copy.
    window_opts = dict(width=1240, height=860, min_size=(900, 640), text_select=True)
    try:
        window = webview.create_window(
            "Job Finder", f"http://127.0.0.1:{port}/", **window_opts)
    except TypeError:  # a pywebview too old to know the argument
        window_opts.pop("text_select")
        logger.info("This pywebview has no text_select; selection stays disabled.")
        window = webview.create_window(
            "Job Finder", f"http://127.0.0.1:{port}/", **window_opts)

    def _on_start():
        # Auto-check on launch (quiet if already current).
        threading.Thread(target=_run_update_flow, args=(window, True), daemon=True).start()

    # Native menu: Updates → Check for Updates…
    menu = []
    try:
        from webview.menu import Menu, MenuAction

        def _manual_check():
            threading.Thread(target=_run_update_flow, args=(window, False), daemon=True).start()

        menu = [Menu("Updates", [MenuAction("Check for Updates…", _manual_check)])]
    except Exception as exc:  # older pywebview without menu support
        logger.info("Menu unavailable (%s) — using startup auto-check only.", exc)

    try:
        try:
            webview.start(_on_start, menu=menu)
        except TypeError:
            # pywebview without the `menu` kwarg
            webview.start(_on_start)
    except Exception as exc:  # noqa: BLE001
        # Windows needs the Edge WebView2 runtime (and .NET via pythonnet) for a
        # native window; Linux needs GTK/Qt WebKit. When that's missing the app
        # itself is fine - only the shell isn't. Serve it in the browser instead
        # of dying, which is what made Job Finder look broken on Windows.
        logger.warning("Native window failed (%s) — falling back to the browser.", exc)
        _run_in_browser(port)


def _run_in_browser(port: int) -> None:
    """Open the app in the default browser and keep the server alive.

    The server runs on a daemon thread, so the main thread must block here or
    the process would exit the moment the browser opens."""
    import webbrowser

    url = f"http://127.0.0.1:{port}/"
    logger.info("Serving Job Finder at %s (browser mode)", url)
    _message_box(
        "Job Finder",
        "Job Finder couldn't open its own window on this system, so it opened "
        f"in your browser instead:\n\n{url}\n\nKeep this program running while "
        "you use it. On Windows, installing the Microsoft Edge WebView2 runtime "
        "restores the native window.",
    )
    try:
        webbrowser.open(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not open a browser (%s) — visit %s manually.", exc, url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Shutting down.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - last line of defence
        _fatal(exc)
