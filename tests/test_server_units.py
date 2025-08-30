from __future__ import annotations

from types import SimpleNamespace

import pytest

from bootServer.server import _HTTPHandler, bootServer


def test__HTTPHandler_log_message_covers():
    """Call the custom log_message to ensure coverage."""
    # Create a minimal fake instance with required attribute
    obj = SimpleNamespace(client_address=("127.0.0.1", 12345))
    # Call the unbound method with our fake object
    _HTTPHandler.log_message(obj, "%s %s", "a", "b")  # type: ignore[arg-type]


def test_bootServer_parse_streams_wrapper():
    """Wrapper method delegates to top-level parse_streams."""
    srv = bootServer(root_dir=".", http_port=0, tftp_port=0, enable_tftp=False)
    res = srv.parse_streams({"pxe": {"format": "ipxe"}})
    assert res["pxe.format"] == "ipxe"


def test_bootServer_start_https_requires_certs(tmp_path):
    """Enabling HTTPS without cert/key raises ValueError."""
    srv = bootServer(
        root_dir=str(tmp_path),
        http_port=0,
        tftp_port=0,
        enable_tftp=False,
        enable_https=True,
        https_port=0,
    )
    with pytest.raises(ValueError):
        srv.start()


def test_bootServer_stop_exception_paths():
    """Stop handles exceptions from sub-server stop() calls without raising."""
    srv = bootServer(root_dir=".", http_port=0, tftp_port=0, enable_tftp=False)

    class _Boom:
        def stop(self) -> None:
            raise RuntimeError("boom")

    # inject fake sub-servers to exercise except branches
    srv._https = _Boom()  # type: ignore[attr-defined]
    srv._http = _Boom()  # type: ignore[attr-defined]
    srv._tftp = _Boom()  # type: ignore[attr-defined]

    # Should not raise, just log exceptions
    srv.stop()
