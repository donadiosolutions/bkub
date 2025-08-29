# ... existing code ...
import socket
import struct
from pathlib import Path

from bootServer import bootServer

def _make_rrq(filename: str, mode: str = "octet") -> bytes:
    return struct.pack("!H", 1) + filename.encode("utf-8") + b"\x00" + mode.encode("utf-8") + b"\x00"

def test_integration_http_and_tftp(tmp_path: Path):
    (tmp_path / "index.html").write_text("ok")
    (tmp_path / "boot.bin").write_bytes(b"bootdata123")
    server = bootServer(root_dir=str(tmp_path), http_port=0, tftp_port=0, enable_tftp=True)
    server.start()
    try:
        http_port = server.http_sock_port
        tftp_port = server.tftp_sock_port

        # HTTP: simple GET
        s = socket.create_connection(("127.0.0.1", http_port), timeout=2.0)
        try:
            s.sendall(b"GET /index.html HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            resp = b""
            while True:
                part = s.recv(4096)
                if not part:
                    break
                resp += part
            assert b"200 OK" in resp
            assert b"ok" in resp
        finally:
            s.close()

        # TFTP: RRQ expecting DATA
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            sock.sendto(_make_rrq("boot.bin"), ("127.0.0.1", tftp_port))
            data, _ = sock.recvfrom(2048)
            opcode, block = struct.unpack("!HH", data[:4])
            assert opcode == 3 and block == 1
        finally:
            sock.close()
    finally:
        server.stop()

    # After stop, ports should be released; try to bind to same ports (ephemeral check)
    # Bind to 127.0.0.1:0 to get an ephemeral port and ensure we can create sockets (sanity)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.close()
