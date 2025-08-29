from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from . import bootServer

LOG = logging.getLogger("bootServer.cli")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="serve-boot-artifacts", description="Serve boot artifacts over HTTP (and optional HTTPS) and TFTP")
    p.add_argument("--root-dir", "-r", default=".", help="Directory to serve files from")
    p.add_argument("--http-port", type=int, default=8080, help="HTTP port (0 for ephemeral)")
    p.add_argument("--tftp-port", type=int, default=69, help="TFTP port (0 for ephemeral)")
    p.add_argument("--no-tftp", dest="enable_tftp", action="store_false", help="Disable TFTP serving")
    p.add_argument("--host", default="0.0.0.0", help="Host/interface to bind")
    # HTTPS options
    p.add_argument("--enable-https", dest="enable_https", action="store_true", help="Enable HTTPS alongside HTTP")
    p.add_argument("--https-port", type=int, default=8443, help="HTTPS port (0 for ephemeral)")
    p.add_argument("--ssl-certfile", type=str, default=None, help="Path to SSL certificate file (PEM)")
    p.add_argument("--ssl-keyfile", type=str, default=None, help="Path to SSL private key file (PEM)")
    p.add_argument("--log-level", default="INFO", help="Logging level")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    root = Path(args.root_dir).resolve()
    if not root.exists():
        LOG.error("root directory does not exist: %s", root)
        return 2

    # If HTTPS requested, ensure cert/key provided
    if args.enable_https and (not args.ssl_certfile or not args.ssl_keyfile):
        LOG.error("HTTPS enabled but --ssl-certfile and --ssl-keyfile must be provided")
        return 2

    server = bootServer(
        root_dir=str(root),
        http_port=args.http_port,
        tftp_port=args.tftp_port,
        logger=LOG,
        host=args.host,
        enable_tftp=bool(args.enable_tftp),
        enable_https=bool(args.enable_https),
        https_port=args.https_port,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
    )

    # graceful shutdown handling
    stop_requested = False

    def _on_signal(signum, frame):
        nonlocal stop_requested
        LOG.info("Received signal %s, stopping...", signum)
        stop_requested = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        server.start()
        LOG.info("Servers started: HTTP=%s TFTP=%s HTTPS=%s", server.http_sock_port, server.tftp_sock_port, server.https_sock_port)
        # wait until signal
        while not stop_requested:
            signal.pause()
    except KeyboardInterrupt:
        LOG.info("Keyboard interrupt received, stopping servers")
    except Exception:
        LOG.exception("Server failed")
        try:
            server.stop()
        except Exception:
            LOG.exception("Error during stop")
        return 1
    finally:
        server.stop()
        LOG.info("Servers stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
