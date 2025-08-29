# ... existing code ...
from __future__ import annotations

import logging
import ssl
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional

LOG = logging.getLogger(__name__)


class HttpFileServer:
    def __init__(self, root_dir: str | Path, host: str = "0.0.0.0", port: int = 80, logger: Optional[logging.Logger] = None) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.host = host
        self.port = port
        self.logger = logger or LOG
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.sock_port: Optional[int] = None

    def start(self) -> None:
        if self._server:
            return
        handler_cls = SimpleHTTPRequestHandler
        server = ThreadingHTTPServer((self.host, self.port), lambda *args, **kwargs: handler_cls(*args, directory=str(self.root_dir), **kwargs))
        self._server = server
        self.sock_port = server.server_address[1]
        self.logger.info("HTTP server serving %s on %s:%d", self.root_dir, self.host, self.sock_port)
        thr = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread = thr
        thr.start()

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                self.logger.exception("Error shutting down HTTP server")
            try:
                self._server.server_close()
            except Exception:
                self.logger.exception("Error closing HTTP server")
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        self.sock_port = None


class HttpsFileServer:
    def __init__(self, root_dir: str | Path, host: str = "0.0.0.0", port: int = 443, certfile: str | None = None, keyfile: str | None = None, logger: Optional[logging.Logger] = None) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.logger = logger or LOG
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.sock_port: Optional[int] = None

    def start(self) -> None:
        if self._server:
            return
        if not self.certfile or not self.keyfile:
            raise ValueError("Both certfile and keyfile are required for HTTPS")
        handler_cls = SimpleHTTPRequestHandler
        server = ThreadingHTTPServer((self.host, self.port), lambda *args, **kwargs: handler_cls(*args, directory=str(self.root_dir), **kwargs))
        # create SSL context with reasonable defaults, require TLS >= 1.2
        ctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            # older Python may not have TLSVersion; ignore if not available
            pass
        ctx.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
        # wrap the existing socket
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        self._server = server
        self.sock_port = server.server_address[1]
        self.logger.info("HTTPS server serving %s on %s:%d", self.root_dir, self.host, self.sock_port)
        thr = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread = thr
        thr.start()

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                self.logger.exception("Error shutting down HTTPS server")
            try:
                self._server.server_close()
            except Exception:
                self.logger.exception("Error closing HTTPS server")
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        self.sock_port = None
# ... existing code ...
