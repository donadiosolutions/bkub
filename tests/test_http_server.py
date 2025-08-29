import socket
import threading
import time
from pathlib import Path

import pytest

from bootServer import bootServer

def _http_get(host: str, port: int, path: str, timeout: float = 2.0) -> bytes:
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("utf-8"))
        s.settimeout(timeout)
        data = b""
        while True:
            part = s.recv(4096)
            if not part:
                break
            data += part
        return data
    finally:
        s.close()

def test_http_serves_file(tmp_path: Path):
    content = b"hello-http"
    fpath = tmp_path / "file.txt"
    fpath.write_bytes(content)

    server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=False)
    server.start()
    try:
        port = server.http_sock_port
        resp = _http_get("127.0.0.1", port, "/file.txt")
        assert b"200 OK" in resp
        assert content in resp
    finally:
        server.stop()

def test_http_block_path_traversal(tmp_path: Path):
    # create a file outside served dir
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"secret")
    server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=False)
    server.start()
    try:
        port = server.http_sock_port
        # attempt to traverse
        resp = _http_get("127.0.0.1", port, "/../outside.txt")
        # should not expose the outside file; expect 404 or 403
        assert b"200 OK" not in resp
    finally:
        server.stop()

def test_http_404_for_missing(tmp_path: Path):
    server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=False)
    server.start()
    try:
        port = server.http_sock_port
        resp = _http_get("127.0.0.1", port, "/no-such-file")
        assert b"404" in resp
    finally:
        server.stop()
