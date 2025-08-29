from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

LOG = logging.getLogger(__name__)


def parse_streams(stream: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    """
    Pure helper that extracts common keys from a 'streams' dict into a normalized mapping.

    Expected input structure examples (partial):
      { "pxe": {"format": "ipxe"}, "disk": {"location": "coreos-x86_64.raw.xz"}, "raw.xz": "file" }

    Returns a mapping with keys:
      - pxe.format -> Optional[str]
      - disk.location -> Optional[str]
      - raw.xz or raw -> Optional[str] (prefers raw.xz then raw)
    """
    result: Dict[str, Optional[str]] = {"pxe.format": None, "disk.location": None, "raw.xz": None, "raw": None}
    # pxe.format
    pxe = stream.get("pxe")
    if isinstance(pxe, Mapping):
        fmt = pxe.get("format")
        if isinstance(fmt, str):
            result["pxe.format"] = fmt
    # disk.location
    disk = stream.get("disk")
    if isinstance(disk, Mapping):
        loc = disk.get("location")
        if isinstance(loc, str):
            result["disk.location"] = loc
    # raw.xz and raw (string or mapping)
    raw_xz = stream.get("raw.xz")
    if isinstance(raw_xz, str):
        result["raw.xz"] = raw_xz
    raw = stream.get("raw")
    if isinstance(raw, str):
        result["raw"] = raw
    # Some feeds may embed disk as string
    if result["disk.location"] is None and isinstance(stream.get("disk"), str):
        result["disk.location"] = stream.get("disk")  # type: ignore[assignment]
    return result


class _HTTPHandler(SimpleHTTPRequestHandler):
    # ensure thread-safe logging
    def log_message(self, format: str, *args: Any) -> None:
        LOG.info("%s - - %s", self.client_address[0], format % args)


class bootServer:
    """
    Main server class that manages an HTTP server and an optional minimal TFTP server.
    """

    OP_RRQ = 1
    OP_DATA = 3
    OP_ACK = 4
    OP_ERROR = 5
    BLOCK_SIZE = 512

    def __init__(
        self,
        root_dir: str,
        http_port: int,
        tftp_port: int,
        logger: Optional[logging.Logger] = None,
        host: str = "0.0.0.0",
        enable_tftp: bool = True,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.http_port = http_port
        self.tftp_port = tftp_port
        self.host = host
        self.enable_tftp = enable_tftp
        self.logger = logger or LOG
        self._http_server: Optional[ThreadingHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._tftp_sock: Optional[socket.socket] = None
        self._tftp_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # instance wrapper for pure helper
    def parse_streams(self, stream: Mapping[str, Any]) -> Dict[str, Optional[str]]:
        return parse_streams(stream)

    def start(self) -> None:
        """Start HTTP and optionally TFTP servers. If port is 0, OS assigns an ephemeral port."""
        self._stop_event.clear()
        self._start_http()
        if self.enable_tftp:
            self._start_tftp()

    def stop(self) -> None:
        """Stop servers and release ports."""
        self._stop_event.set()
        # stop HTTP
        if self._http_server:
            try:
                self._http_server.shutdown()
            except Exception:
                self.logger.exception("Error shutting down HTTP server")
            try:
                self._http_server.server_close()
            except Exception:
                self.logger.exception("Error closing HTTP server")
            self._http_server = None
        if self._http_thread and self._http_thread.is_alive():
            self._http_thread.join(timeout=2.0)
            self._http_thread = None
        # stop TFTP
        if self._tftp_sock:
            try:
                # sending a dummy packet to unblock recvfrom
                try:
                    self._tftp_sock.sendto(b"", (self.host, self.tftp_sock_port))
                except Exception:
                    pass
                self._tftp_sock.close()
            except Exception:
                self.logger.exception("Error closing TFTP socket")
            self._tftp_sock = None
        if self._tftp_thread and self._tftp_thread.is_alive():
            self._tftp_thread.join(timeout=2.0)
            self._tftp_thread = None

    # HTTP
    def _start_http(self) -> None:
        handler_cls = _HTTPHandler
        # ThreadingHTTPServer supports passing 'directory' via handler constructor in 3.7+.
        server = ThreadingHTTPServer((self.host, self.http_port), lambda *args, **kwargs: handler_cls(*args, directory=str(self.root_dir), **kwargs))
        self._http_server = server
        # if port was 0, determine assigned port
        self.http_sock_port = server.server_address[1]
        self.logger.info("HTTP server serving %s on %s:%d", self.root_dir, self.host, self.http_sock_port)
        thr = threading.Thread(target=server.serve_forever, daemon=True)
        self._http_thread = thr
        thr.start()

    # TFTP minimal implementation
    def _start_tftp(self) -> None:
        # create UDP socket and bind
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.tftp_port))
        self._tftp_sock = sock
        # store real bound port
        self.tftp_sock_port = sock.getsockname()[1]
        self.logger.info("TFTP server serving %s on %s:%d", self.root_dir, self.host, self.tftp_sock_port)
        thr = threading.Thread(target=self._tftp_serve_loop, args=(sock,), daemon=True)
        self._tftp_thread = thr
        thr.start()

    def _tftp_serve_loop(self, sock: socket.socket) -> None:
        sock.settimeout(1.0)
        while not self._stop_event.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            # handle each request in background
            threading.Thread(target=self._handle_tftp_request, args=(data, addr), daemon=True).start()

    def _handle_tftp_request(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            if len(data) < 2:
                self._send_tftp_error(self._tftp_sock, addr, 0, "Invalid packet")
                return
            opcode = struct.unpack("!H", data[:2])[0]
            if opcode != self.OP_RRQ:
                self._send_tftp_error(self._tftp_sock, addr, 4, "Illegal TFTP operation")
                return
            parts = data[2:].split(b"\x00")
            if not parts or len(parts) < 2:
                self._send_tftp_error(self._tftp_sock, addr, 0, "Malformed RRQ")
                return
            filename = parts[0].decode("utf-8", errors="ignore")
            mode = parts[1].decode("utf-8", errors="ignore") if len(parts) > 1 else "octet"
            self.logger.info("TFTP RRQ from %s:%d -> %s (%s)", addr[0], addr[1], filename, mode)
            if mode.lower() not in ("octet", "binary"):
                self._send_tftp_error(self._tftp_sock, addr, 0, "Only octet mode supported")
                return
            # resolve safe path
            candidate = (self.root_dir / filename.lstrip("/")).resolve()
            try:
                if not str(candidate).startswith(str(self.root_dir)):
                    self._send_tftp_error(self._tftp_sock, addr, 2, "Access violation")
                    return
            except Exception:
                self._send_tftp_error(self._tftp_sock, addr, 2, "Access violation")
                return
            if not candidate.is_file():
                self._send_tftp_error(self._tftp_sock, addr, 1, "File not found")
                return
            # Transfer using a per-transfer socket (client expects data from a new ephemeral port)
            with open(candidate, "rb") as f:
                block_num = 1
                while True:
                    chunk = f.read(self.BLOCK_SIZE)
                    data_pkt = struct.pack("!HH", self.OP_DATA, block_num) + chunk
                    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        tx.sendto(data_pkt, addr)
                        tx.settimeout(5.0)
                        try:
                            ack, _ = tx.recvfrom(4)
                        except socket.timeout:
                            self.logger.warning("Timeout waiting for ACK from %s:%d", addr[0], addr[1])
                            break
                        if len(ack) < 4:
                            self.logger.warning("Short ACK received from %s:%d", addr[0], addr[1])
                            break
                        ack_opcode, ack_block = struct.unpack("!HH", ack[:4])
                        if ack_opcode != self.OP_ACK or ack_block != block_num:
                            self.logger.warning("Unexpected ACK %s %s from %s:%d", ack_opcode, ack_block, addr[0], addr[1])
                            break
                    finally:
                        tx.close()
                    if len(chunk) < self.BLOCK_SIZE:
                        break
                    block_num = (block_num + 1) % 65536
            self.logger.info("Completed TFTP transfer %s -> %s:%d", filename, addr[0], addr[1])
        except Exception:
            self.logger.exception("Error handling TFTP request")
            if self._tftp_sock:
                self._send_tftp_error(self._tftp_sock, addr, 0, "Server error")

    def _send_tftp_error(self, sock: socket.socket | None, addr: tuple[str, int], code: int, message: str) -> None:
        if not sock:
            return
        try:
            pkt = struct.pack("!H", self.OP_ERROR) + struct.pack("!H", code) + message.encode("utf-8") + b"\x00"
            sock.sendto(pkt, addr)
        except Exception:
            self.logger.exception("Failed to send TFTP error to %s:%d", addr[0], addr[1])
