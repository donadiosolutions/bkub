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
import ssl
#
# import extracted servers
from .http_server import HttpFileServer, HttpsFileServer
from .tftp_server import TftpServer

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
        enable_https: bool = False,
        https_port: int = 0,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.http_port = http_port
        self.tftp_port = tftp_port
        self.host = host
        self.enable_tftp = enable_tftp
        self.enable_https = enable_https
        self.https_port = https_port
        self.ssl_certfile = ssl_certfile
        self.ssl_keyfile = ssl_keyfile
        self.logger = logger or LOG
        self._http: Optional[HttpFileServer] = None
        self._https: Optional[HttpsFileServer] = None
        self._tftp: Optional[TftpServer] = None
        self._stop_event = threading.Event()
        # public port properties (None until bound / if disabled)
        self.http_sock_port: Optional[int] = None
        self.tftp_sock_port: Optional[int] = None
        self.https_sock_port: Optional[int] = None

    # instance wrapper for pure helper
    def parse_streams(self, stream: Mapping[str, Any]) -> Dict[str, Optional[str]]:
        return parse_streams(stream)

    def start(self) -> None:
        """Start HTTP and optionally TFTP servers. If port is 0, OS assigns an ephemeral port."""
        self._stop_event.clear()
        # start HTTP
        self._http = HttpFileServer(self.root_dir, host=self.host, port=self.http_port, logger=self.logger)
        self._http.start()
        self.http_sock_port = self._http.sock_port
        # optionally start HTTPS (concurrent) if requested and cert/key provided
        if self.enable_https:
            if not (self.ssl_certfile and self.ssl_keyfile):
                raise ValueError("HTTPS enabled but certfile/keyfile not provided")
            self._https = HttpsFileServer(self.root_dir, host=self.host, port=self.https_port, certfile=self.ssl_certfile, keyfile=self.ssl_keyfile, logger=self.logger)
            self._https.start()
            self.https_sock_port = self._https.sock_port
        else:
            self.https_sock_port = None
        # optionally start TFTP
        if self.enable_tftp:
            self._tftp = TftpServer(self.root_dir, host=self.host, port=self.tftp_port, logger=self.logger)
            self._tftp.start()
            self.tftp_sock_port = self._tftp.sock_port
        else:
            self.tftp_sock_port = None

    def stop(self) -> None:
        """Stop servers and release ports."""
        self._stop_event.set()
        # stop HTTPS
        if self._https:
            try:
                self._https.stop()
            except Exception:
                self.logger.exception("Error stopping HTTPS server")
            self._https = None
            self.https_sock_port = None
        # stop HTTP
        if self._http:
            try:
                self._http.stop()
            except Exception:
                self.logger.exception("Error stopping HTTP server")
            self._http = None
            self.http_sock_port = None
        # stop TFTP
        if self._tftp:
            try:
                self._tftp.stop()
            except Exception:
                self.logger.exception("Error stopping TFTP server")
            self._tftp = None
            self.tftp_sock_port = None
