from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bootServer.http_server import HttpFileServer, HttpsFileServer


def test_http_start_idempotent(tmp_path: Path) -> None:
    """Starting twice keeps the same bound port and does not crash."""
    srv = HttpFileServer(tmp_path, host="127.0.0.1", port=0)
    try:
        srv.start()
        first_port = srv.sock_port
        # Calling start again should be a no-op (early return)
        srv.start()
        assert srv.sock_port == first_port
    finally:
        srv.stop()


def test_http_stop_with_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop swallows shutdown/server_close exceptions and joins thread."""
    srv = HttpFileServer(".")
    # Inject fake server to force exception paths

    class _FakeSrv:
        def shutdown(self) -> None:
            raise RuntimeError("boom-shutdown")

        def server_close(self) -> None:
            raise RuntimeError("boom-close")

        server_address = ("127.0.0.1", 0)

    srv._server = _FakeSrv()  # type: ignore[attr-defined]
    # Fake thread that's alive so join path is taken
    joined = SimpleNamespace(calls=0)

    class _FakeThread:
        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            joined.calls += 1

    srv._thread = _FakeThread()  # type: ignore[attr-defined]
    # Now stop should exercise exception handlers and join block
    srv.stop()
    assert joined.calls == 1


def test_https_start_idempotent_and_missing_certs(tmp_path: Path) -> None:
    """HTTPS requires cert/key; if already started, start() is a no-op."""
    srv = HttpsFileServer(tmp_path, host="127.0.0.1", port=0, certfile=None, keyfile=None)
    with pytest.raises(ValueError):
        srv.start()
    # Prepare valid minimal object and test idempotent start
    # Generate temporary empty files to satisfy load_cert_chain path (won't be loaded because we won't start)
    c = tmp_path / "c.pem"
    k = tmp_path / "k.pem"
    c.write_text("x")
    k.write_text("y")
    srv2 = HttpsFileServer(tmp_path, host="127.0.0.1", port=0, certfile=str(c), keyfile=str(k))
    # We won't actually try to start TLS here (certs invalid), but we can set _server to test idempotent early return
    srv2._server = SimpleNamespace(server_address=("127.0.0.1", 0))  # type: ignore[attr-defined]
    srv2.start()  # early-return branch


def test_https_minimum_version_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fallback path when ssl.TLSVersion is missing is exercised before cert load fails."""
    # Create dummy cert/key; we won't validate them, but server will attempt to load
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("-----BEGIN CERT-----\nX\n-----END CERT-----\n")
    key.write_text("-----BEGIN KEY-----\nY\n-----END KEY-----\n")

    # Monkeypatch ssl.TLSVersion to None to trigger fallback except branch
    import ssl as _ssl

    monkeypatch.setattr(_ssl, "TLSVersion", None, raising=False)
    srv = HttpsFileServer(tmp_path, host="127.0.0.1", port=0, certfile=str(cert), keyfile=str(key))

    # We expect load_cert_chain to fail due to invalid content, but the path to set minimum_version should be exercised
    with pytest.raises(Exception):
        srv.start()


def test_https_stop_with_exceptions() -> None:
    """HTTPS stop swallows exceptions and joins background thread."""
    srv = HttpsFileServer(".", certfile="c", keyfile="k")

    class _FakeSrv:
        def shutdown(self) -> None:
            raise RuntimeError("boom-shutdown")

        def server_close(self) -> None:
            raise RuntimeError("boom-close")

        server_address = ("127.0.0.1", 0)

    srv._server = _FakeSrv()  # type: ignore[attr-defined]
    joined = {"calls": 0}

    class _Thread:
        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            joined["calls"] += 1

    srv._thread = _Thread()  # type: ignore[attr-defined]
    srv.stop()
    assert joined["calls"] == 1
