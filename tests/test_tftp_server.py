import socket
import struct
import time
from pathlib import Path

import pytest

from bootServer import bootServer

def _make_rrq(filename: str, mode: str = "octet") -> bytes:
    return struct.pack("!H", 1) + filename.encode("utf-8") + b"\x00" + mode.encode("utf-8") + b"\x00"

def test_tftp_rrq_returns_data(tmp_path: Path):
    content = b"abcdefgh" * 100  # less than many blocks
    f = tmp_path / "boot.img"
    f.write_bytes(content)
    server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=True)
    server.start()
    try:
        port = server.tftp_sock_port
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            sock.sendto(_make_rrq("boot.img"), ("127.0.0.1", port))
            data, _ = sock.recvfrom(2048)
            # expect DATA packet opcode 3 and block 1
            opcode, block = struct.unpack("!HH", data[:4])
            assert opcode == 3
            assert block == 1
        finally:
            sock.close()
    finally:
        server.stop()

def test_tftp_missing_file_returns_error(tmp_path: Path):
    server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=True)
    server.start()
    try:
        port = server.tftp_sock_port
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            sock.sendto(_make_rrq("no-such"), ("127.0.0.1", port))
            data, _ = sock.recvfrom(2048)
            opcode = struct.unpack("!H", data[:2])[0]
            assert opcode == 5  # ERROR
        finally:
            sock.close()
    finally:
        server.stop()

def test_tftp_not_enabled_does_not_bind(tmp_path: Path):
    server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=False)
    server.start()
    try:
        # public API: tftp_sock_port should be None when TFTP is not enabled
        assert server.tftp_sock_port is None
    finally:
        server.stop()
