from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

import bootServer.tftp_server as tftp_mod
from bootServer.tftp_server import TftpServer


def _rrq(name: str, mode: str = "octet") -> bytes:
    return struct.pack("!H", TftpServer.OP_RRQ) + name.encode() + b"\x00" + mode.encode() + b"\x00"


def _parse_opcode(pkt: bytes) -> int:
    return struct.unpack("!H", pkt[:2])[0]


def test_tftp_start_idempotent(tmp_path: Path) -> None:
    """Starting twice should be a no-op and keep the same port."""
    srv = TftpServer(tmp_path, host="127.0.0.1", port=0)
    srv.start()
    try:
        port1 = srv.sock_port
        srv.start()  # should return early
        assert srv.sock_port == port1
    finally:
        srv.stop()


def test_tftp_stop_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop swallows socket send/close exceptions and still joins thread."""
    srv = TftpServer(".")

    class _Sock:
        def __init__(self) -> None:
            self.addr = ("127.0.0.1", 0)

        def sendto(self, data: bytes, addr) -> None:  # pragma: no cover - exception path below
            raise RuntimeError("sendto fail")

        def close(self) -> None:
            raise RuntimeError("close fail")

        def getsockname(self):
            return ("127.0.0.1", 0)

    srv._sock = _Sock()  # type: ignore[attr-defined]
    # Thread alive to exercise join

    class _Thread:
        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            pass

    srv._thread = _Thread()  # type: ignore[attr-defined]
    srv.sock_port = 0
    srv.stop()  # should swallow exceptions and proceed


def test_handle_request_invalid_and_illegal(tmp_path: Path) -> None:
    """Invalid and illegal opcodes produce ERROR packets."""
    srv = TftpServer(tmp_path)
    sent = SimpleNamespace(pkt=b"")

    class _Sock:
        def sendto(self, data: bytes, addr) -> None:
            sent.pkt = data

    srv._sock = _Sock()  # type: ignore[attr-defined]
    # Too short
    srv._handle_request(b"\x00", ("127.0.0.1", 1234))
    assert _parse_opcode(sent.pkt) == TftpServer.OP_ERROR
    # Illegal opcode
    sent.pkt = b""
    srv._handle_request(struct.pack("!H", 9) + b"foo\x00bar\x00", ("127.0.0.1", 1234))
    assert _parse_opcode(sent.pkt) == TftpServer.OP_ERROR


def test_handle_request_malformed_and_wrong_mode(tmp_path: Path) -> None:
    """Malformed RRQ and unsupported mode produce ERROR packets."""
    srv = TftpServer(tmp_path)
    sent = SimpleNamespace(pkt=b"")

    class _Sock:
        def sendto(self, data: bytes, addr) -> None:
            sent.pkt = data

    srv._sock = _Sock()  # type: ignore[attr-defined]
    # Malformed RRQ (no terminators/parts)
    srv._handle_request(struct.pack("!H", 1) + b"onlyname", ("127.0.0.1", 9999))
    assert _parse_opcode(sent.pkt) == TftpServer.OP_ERROR
    # Unsupported mode
    srv._handle_request(_rrq("file", mode="netascii"), ("127.0.0.1", 9999))
    assert _parse_opcode(sent.pkt) == TftpServer.OP_ERROR


def test_handle_request_access_violation(tmp_path: Path) -> None:
    """Path traversal outside root returns ERROR (access violation)."""
    srv = TftpServer(tmp_path)
    sent = SimpleNamespace(pkt=b"")

    class _Sock:
        def sendto(self, data: bytes, addr) -> None:
            sent.pkt = data

    srv._sock = _Sock()  # type: ignore[attr-defined]
    srv._handle_request(_rrq("../secret"), ("127.0.0.1", 9999))
    assert _parse_opcode(sent.pkt) == TftpServer.OP_ERROR


def test_send_error_failure_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """_send_error swallows sendto exceptions and only logs."""
    srv = TftpServer(".")

    class _BadSock:
        def sendto(self, data: bytes, addr) -> None:
            raise RuntimeError("boom")

    # Should not raise
    srv._send_error(_BadSock(), ("127.0.0.1", 1), 0, "x")  # type: ignore[arg-type]


def test_transfer_ack_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Short ACK path exercised; handler completes without raising."""
    # Create a file to trigger transfer path
    f = tmp_path / "boot.bin"
    f.write_bytes(b"DATA")

    srv = TftpServer(tmp_path)

    # Socket used for sending error responses (not used in success path but required to exist)
    srv._sock = SimpleNamespace(sendto=lambda d, a: None)  # type: ignore[attr-defined]

    # Prepare a fake UDP socket for the transfer that returns a short ACK
    class _FakeTx:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def sendto(self, data: bytes, addr) -> None:
            self._sent = data

        def settimeout(self, t: float) -> None:
            pass

        def recvfrom(self, n: int):
            # Return a short ack first to hit the short-ack branch
            return (b"\x00\x04\x00", ("127.0.0.1", 1234))

        def close(self) -> None:
            pass

    monkeypatch.setattr(tftp_mod.socket, "socket", _FakeTx)  # type: ignore[arg-type]
    # Should complete without raising
    srv._handle_request(_rrq("boot.bin"), ("127.0.0.1", 9999))


def test_tftp_serve_loop_timeout(tmp_path: Path) -> None:
    """Serve loop handles recvfrom timeout and continues until stopped."""
    srv = TftpServer(tmp_path, host="127.0.0.1", port=0)
    srv.start()
    try:
        # Wait a bit to allow recvfrom timeout path to run at least once
        import time

        time.sleep(1.2)
    finally:
        srv.stop()


def test_tftp_path_compare_exception(tmp_path: Path) -> None:
    """Exception during path safety comparison results in access violation error."""
    srv = TftpServer(tmp_path)
    sent = {"pkt": b""}

    class _Sock:
        def sendto(self, data: bytes, addr) -> None:
            sent["pkt"] = data

    class _BadRoot:
        def __truediv__(self, other):
            return self

        def resolve(self):
            return self

        def __str__(self) -> str:  # force exception during str(self.root_dir)
            raise RuntimeError("bad root")

    srv.root_dir = _BadRoot()  # type: ignore[assignment]
    srv._sock = _Sock()  # type: ignore[attr-defined]
    srv._handle_request(_rrq("file.bin"), ("127.0.0.1", 7))
    assert _parse_opcode(sent["pkt"]) == TftpServer.OP_ERROR


def test_tftp_ack_timeout_and_unexpected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout waiting for ACK and unexpected ACK opcode/block are handled with warnings."""
    # File smaller than one block
    f = tmp_path / "x.bin"
    f.write_bytes(b"HELLO")
    srv = TftpServer(tmp_path)
    srv._sock = SimpleNamespace(sendto=lambda d, a: None)  # type: ignore[attr-defined]

    # First, simulate timeout waiting for ACK
    class _TxTimeout:
        def __init__(self, *a, **k):
            pass

        def sendto(self, d, a):
            pass

        def settimeout(self, t):
            pass

        def recvfrom(self, n):
            raise tftp_mod.socket.timeout

        def close(self):
            pass

    monkeypatch.setattr(tftp_mod.socket, "socket", _TxTimeout)  # type: ignore[arg-type]
    srv._handle_request(_rrq("x.bin"), ("127.0.0.1", 1))

    # Next, simulate unexpected ACK opcode/block
    class _TxUnexpected:
        def __init__(self, *a, **k):
            pass

        def sendto(self, d, a):
            pass

        def settimeout(self, t):
            pass

        def recvfrom(self, n):
            # opcode=4 but wrong block (2)
            return (b"\x00\x04\x00\x02", ("127.0.0.1", 2))

        def close(self):
            pass

    monkeypatch.setattr(tftp_mod.socket, "socket", _TxUnexpected)  # type: ignore[arg-type]
    srv._handle_request(_rrq("x.bin"), ("127.0.0.1", 2))


def test_tftp_valid_ack_and_exception_in_sendto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid ACK path ends transfer; then trigger exception in sendto to exercise outer handler."""
    # For valid ack path reaching len(chunk) < BLOCK_SIZE
    f = tmp_path / "y.bin"
    f.write_bytes(b"Z")
    srv = TftpServer(tmp_path)
    srv._sock = SimpleNamespace(sendto=lambda d, a: None)  # type: ignore[attr-defined]

    class _TxOk:
        def __init__(self, *a, **k):
            pass

        def sendto(self, d, a):
            pass

        def settimeout(self, t):
            pass

        def recvfrom(self, n):
            # Proper ACK for block 1
            return (b"\x00\x04\x00\x01", ("127.0.0.1", 3))

        def close(self):
            pass

    monkeypatch.setattr(tftp_mod.socket, "socket", _TxOk)  # type: ignore[arg-type]
    srv._handle_request(_rrq("y.bin"), ("127.0.0.1", 3))

    # Now raise in sendto to exercise outer exception handler (and Server error path)
    class _TxBoom:
        def __init__(self, *a, **k):
            pass

        def sendto(self, d, a):
            raise RuntimeError("boom")

        def settimeout(self, t):
            pass

        def recvfrom(self, n):
            return (b"\x00\x04\x00\x01", ("127.0.0.1", 3))

        def close(self):
            pass

    # Ensure _send_error is called (sock present)
    sent = {"called": False}

    class _ErrSock:
        def sendto(self, d, a):
            sent["called"] = True

    srv._sock = _ErrSock()  # type: ignore[assignment]
    monkeypatch.setattr(tftp_mod.socket, "socket", _TxBoom)  # type: ignore[arg-type]
    # Should not raise
    srv._handle_request(_rrq("y.bin"), ("127.0.0.1", 4))
    assert sent["called"] is True


def test_tftp_multiblock_increments_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Send a file > BLOCK_SIZE to exercise block number increment path."""
    # Create a file of size > BLOCK_SIZE to force next-block increment path
    f = tmp_path / "big.bin"
    f.write_bytes(b"A" * (TftpServer.BLOCK_SIZE + 10))
    srv = TftpServer(tmp_path)
    srv._sock = SimpleNamespace(sendto=lambda d, a: None)  # type: ignore[attr-defined]

    class _TxAckAll:
        def __init__(self, *a, **k):
            self.calls = 0

        def sendto(self, d, a):
            pass

        def settimeout(self, t):
            pass

        def recvfrom(self, n):
            # Always ack the current block number in the last data packet sent
            self.calls += 1
            # For simplicity, always ACK block 1; sufficient for coverage to hit increment
            return (b"\x00\x04\x00\x01", ("127.0.0.1", 5))

        def close(self):
            pass

    monkeypatch.setattr(tftp_mod.socket, "socket", _TxAckAll)  # type: ignore[arg-type]
    srv._handle_request(_rrq("big.bin"), ("127.0.0.1", 5))


def test_tftp_send_error_none_guard() -> None:
    """_send_error with None socket should simply return without error."""
    srv = TftpServer(".")
    # Should simply return without error
    srv._send_error(None, ("127.0.0.1", 9), 0, "msg")
