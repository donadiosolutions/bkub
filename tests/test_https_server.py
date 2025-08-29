from __future__ import annotations

import os
import shutil
import socket
import ssl
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from bootServer import bootServer

def _http_get_tls(host: str, port: int, path: str, timeout: float = 2.0) -> bytes:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        ss = ctx.wrap_socket(s, server_hostname=host)
        try:
            ss.sendall(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("utf-8"))
            ss.settimeout(timeout)
            data = b""
            while True:
                part = ss.recv(4096)
                if not part:
                    break
                data += part
            return data
        finally:
            ss.close()
    finally:
        s.close()

@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl not available to create test cert")
def test_https_serves_file(tmp_path: Path):
    # create self-signed cert using openssl
    with TemporaryDirectory() as td:
        td_path = Path(td)
        key = td_path / "key.pem"
        cert = td_path / "cert.pem"
        # generate key and cert (rsa 2048, self-signed, valid 1 day)
        subprocess.check_call([
            "openssl", "req", "-x509", "-nodes", "-days", "1",
            "-newkey", "rsa:2048",
            "-subj", "/CN=127.0.0.1",
            "-keyout", str(key),
            "-out", str(cert),
        ])
        # prepare served file
        (tmp_path / "index.html").write_text("secure-ok")
        # start server with HTTPS enabled
        server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=False, enable_https=True, https_port=0, ssl_certfile=str(cert), ssl_keyfile=str(key))
        server.start()
        try:
            port = server.https_sock_port
            assert port is not None
            resp = _http_get_tls("127.0.0.1", port, "/index.html")
            assert b"200 OK" in resp
            assert b"secure-ok" in resp
        finally:
            server.stop()
