from __future__ import annotations

import logging
import socket
import struct
import threading
from pathlib import Path
from typing import Optional, Tuple

LOG = logging.getLogger(__name__)


class TftpServer:
    OP_RRQ = 1
    OP_DATA = 3
    OP_ACK = 4
    OP_ERROR = 5
    BLOCK_SIZE = 512

    def __init__(
        self, root_dir: str | Path, host: str = "0.0.0.0", port: int = 69, logger: Optional[logging.Logger] = None
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.host = host
        self.port = port
        self.logger = logger or LOG
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.sock_port: Optional[int] = None

    def start(self) -> None:
        if self._sock:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.port))
        self._sock = sock
        self.sock_port = sock.getsockname()[1]
        self.logger.info("TFTP server serving %s on %s:%d", self.root_dir, self.host, self.sock_port)
        thr = threading.Thread(target=self._serve_loop, args=(sock,), daemon=True)
        self._thread = thr
        self._stop_event.clear()
        thr.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock:
            try:
                # send dummy packet to unblock recvfrom
                try:
                    self._sock.sendto(b"", (self.host, self.sock_port or self.port))
                except Exception:
                    pass
                self._sock.close()
            except Exception:
                self.logger.exception("Error closing TFTP socket")
            self._sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        self.sock_port = None

    def _serve_loop(self, sock: socket.socket) -> None:
        sock.settimeout(1.0)
        while not self._stop_event.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_request, args=(data, addr), daemon=True).start()

    def _handle_request(self, data: bytes, addr: Tuple[str, int]) -> None:
        try:
            if len(data) < 2:
                self._send_error(self._sock, addr, 0, "Invalid packet")
                return
            opcode = struct.unpack("!H", data[:2])[0]
            if opcode != self.OP_RRQ:
                self._send_error(self._sock, addr, 4, "Illegal TFTP operation")
                return
            parts = data[2:].split(b"\x00")
            if not parts or len(parts) < 2:
                self._send_error(self._sock, addr, 0, "Malformed RRQ")
                return
            filename = parts[0].decode("utf-8", errors="ignore")
            mode = parts[1].decode("utf-8", errors="ignore") if len(parts) > 1 else "octet"
            self.logger.info("TFTP RRQ from %s:%d -> %s (%s)", addr[0], addr[1], filename, mode)
            if mode.lower() not in ("octet", "binary"):
                self._send_error(self._sock, addr, 0, "Only octet mode supported")
                return
            # resolve safe path
            candidate = (self.root_dir / filename.lstrip("/")).resolve()
            try:
                if not str(candidate).startswith(str(self.root_dir)):
                    self._send_error(self._sock, addr, 2, "Access violation")
                    return
            except Exception:
                self._send_error(self._sock, addr, 2, "Access violation")
                return
            if not candidate.is_file():
                self._send_error(self._sock, addr, 1, "File not found")
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
                            self.logger.warning(
                                "Unexpected ACK %s %s from %s:%d", ack_opcode, ack_block, addr[0], addr[1]
                            )
                            break
                    finally:
                        tx.close()
                    if len(chunk) < self.BLOCK_SIZE:
                        break
                    block_num = (block_num + 1) % 65536
            self.logger.info("Completed TFTP transfer %s -> %s:%d", filename, addr[0], addr[1])
        except Exception:
            self.logger.exception("Error handling TFTP request")
            if self._sock:
                self._send_error(self._sock, addr, 0, "Server error")

    def _send_error(self, sock: Optional[socket.socket], addr: Tuple[str, int], code: int, message: str) -> None:
        if not sock:
            return
        try:
            pkt = struct.pack("!H", self.OP_ERROR) + struct.pack("!H", code) + message.encode("utf-8") + b"\x00"
            sock.sendto(pkt, addr)
        except Exception:
            self.logger.exception("Failed to send TFTP error to %s:%d", addr[0], addr[1])
