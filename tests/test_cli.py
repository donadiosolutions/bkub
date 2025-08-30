from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest


class _FakeServer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = 0
        self.http_sock_port = 1234
        self.tftp_sock_port = None
        self.https_sock_port = None

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped += 1


def test_cli_root_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI exits 2 when root directory does not exist."""
    from bootServer import cli

    code = cli.main(["--root-dir", str(tmp_path / "nope"), "--no-tftp", "--http-port", "0"])
    assert code == 2


def test_cli_https_without_certs(tmp_path: Path) -> None:
    """CLI exits 2 when HTTPS enabled without cert/key arguments."""
    from bootServer import cli

    code = cli.main(
        [
            "--root-dir",
            str(tmp_path),
            "--enable-https",
            "--https-port",
            "0",
            "--no-tftp",
            "--http-port",
            "0",
        ]
    )
    assert code == 2


def test_cli_keyboard_interrupt_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Signal handler toggles stop flag and exits cleanly on KeyboardInterrupt."""
    from bootServer import cli

    fake = _FakeServer()
    monkeypatch.setattr(cli, "bootServer", lambda **kwargs: fake)
    # Make signal.pause immediately raise KeyboardInterrupt to exit the loop
    import signal as _signal

    monkeypatch.setattr(_signal, "pause", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))

    code = cli.main(["--root-dir", str(tmp_path), "--no-tftp", "--http-port", "0"])
    # stop should be called in finally even after KeyboardInterrupt
    assert code == 0
    assert fake.started is True
    assert fake.stopped >= 1


def test_cli_exception_in_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Start failure returns exit code 1 and attempts stop."""
    from bootServer import cli

    class _Boom(_FakeServer):
        def start(self) -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    boom = _Boom()
    monkeypatch.setattr(cli, "bootServer", lambda **kwargs: boom)

    code = cli.main(["--root-dir", str(tmp_path), "--no-tftp", "--http-port", "0"])
    assert code == 1
    # stop is attempted in except and again in finally; ensure our stop was called
    assert boom.stopped >= 1


def test_cli_module_main_sys_exit_help(monkeypatch: pytest.MonkeyPatch) -> None:
    """Import bootServer.cli fresh with runpy to hit sys.exit(main())."""
    argv = ["python", "-m", "bootServer.cli", "--help"]
    monkeypatch.setattr(sys, "argv", argv)
    # Remove any prior import to avoid runpy warning about existing module
    sys.modules.pop("bootServer.cli", None)
    with pytest.raises(SystemExit) as se:
        runpy.run_module("bootServer.cli", run_name="__main__")
    assert se.value.code == 0 or se.value.code is None


def test_launcher_script_under_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run repository launcher under coverage and assert sys.exit(0)."""
    launcher = Path.cwd() / "serve-boot-artifacts"
    assert launcher.exists()
    # Avoid executing bootServer.__main__ (which would sys.exit) so we can reach the launcher sys.exit(0)
    monkeypatch.setattr(runpy, "run_module", lambda *a, **k: None)
    with pytest.raises(SystemExit) as se:
        runpy.run_path(str(launcher), run_name="__main__")
    assert se.value.code == 0 or se.value.code is None


def test_cli_signal_handler_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Capture installed signal handler and ensure it flips the stop flag once."""
    from bootServer import cli

    fake = _FakeServer()
    monkeypatch.setattr(cli, "bootServer", lambda **kwargs: fake)

    import signal as _signal

    captured = {}

    def _capture(sig, handler):
        captured[sig] = handler

    monkeypatch.setattr(_signal, "signal", _capture)  # capture the handler

    # pause will invoke the captured SIGINT handler once, then raise KeyboardInterrupt to exit
    def _pause_once():
        handler = captured.get(_signal.SIGINT) or captured.get(_signal.SIGTERM)
        assert handler is not None
        handler(_signal.SIGINT, None)
        raise KeyboardInterrupt

    monkeypatch.setattr(_signal, "pause", _pause_once)

    code = cli.main(["--root-dir", str(tmp_path), "--no-tftp", "--http-port", "0"])
    assert code == 0
    assert fake.started is True
    assert fake.stopped >= 1


def test_cli_exception_and_stop_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exception during start triggers stop; first stop raises, second succeeds; exit code 1."""
    from bootServer import cli

    class _Boom(_FakeServer):
        def __init__(self) -> None:
            super().__init__()
            self._stops = 0

        def start(self) -> None:  # type: ignore[override]
            raise RuntimeError("boom start")

        def stop(self) -> None:  # type: ignore[override]
            self._stops += 1
            if self._stops == 1:
                raise RuntimeError("boom stop")
            # second call succeeds

    boom = _Boom()
    monkeypatch.setattr(cli, "bootServer", lambda **kwargs: boom)

    code = cli.main(["--root-dir", str(tmp_path), "--no-tftp", "--http-port", "0"])
    assert code == 1
