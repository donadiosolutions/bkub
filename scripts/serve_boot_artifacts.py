#!/usr/bin/env python3
"""
Simple HTTP + TFTP server to serve the boot-artifacts directory.

Usage:
  ./scripts/serve_boot_artifacts.py --dir ./boot-artifacts --http-port 8080 --tftp-port 69

Notes:
- Running a TFTP server on port 69 requires root privileges. Use a higher port for unprivileged testing.
- The script serves files relative to the provided directory and logs requests.
"""
# ... existing code ...
import argparse
import logging
import os
import sys
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

# Minimal TFTP server implementation (RFC 1350 subset) suitable for read-only serving.
# For production use, prefer a dedicated TFTP server.
import socket
import struct

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class HTTPHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        logging.info("%s - - %s", self.client_address[0], format % args)


def start_http_server(directory: str, port: int):
    os.chdir(directory)
    server = ThreadingHTTPServer(("0.0.0.0", port), HTTPHandler)
    logging.info("HTTP server serving %s on :%d", directory, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        logging.info("HTTP server stopped")


# Simple read-only TFTP server (supports RRQ only). Not feature-complete.
class TFTPServer:
    OP_RRQ = 1
    OP_DATA = 3
    OP_ACK = 4
    OP_ERROR = 5
    BLOCK_SIZE = 512

    def __init__(self, directory: str, host: str = "0.0.0.0", port: int = 6969):
        self.directory = os.path.abspath(directory)
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        logging.info("TFTP server serving %s on %s:%d", self.directory, host, port)

    def serve_forever(self):
        try:
            while True:
                data, addr = self.sock.recvfrom(2048)
                threading.Thread(target=self.handle_request, args=(data, addr), daemon=True).start()
        except KeyboardInterrupt:
            logging.info("TFTP server stopping")
        finally:
            self.sock.close()

    def handle_request(self, data: bytes, addr):
        # Parse RRQ: 2 bytes opcode, then "filename", 0, "mode", 0
        try:
            opcode = struct.unpack("!H", data[:2])[0]
            if opcode != self.OP_RRQ:
                self.send_error(addr, 4, "Illegal TFTP operation")
                return
            parts = data[2:].split(b'\x00')
            filename = parts[0].decode('utf-8')
            mode = parts[1].decode('utf-8') if len(parts) > 1 else "octet"
            logging.info("TFTP RRQ from %s:%d -> %s (%s)", addr[0], addr[1], filename, mode)
            # Only support octet (binary) mode
            if mode.lower() not in ("octet", "binary"):
                self.send_error(addr, 0, "Only octet mode supported")
                return
            # Prevent directory traversal
            safe_path = os.path.normpath(os.path.join(self.directory, filename.lstrip("/")))
            if not safe_path.startswith(self.directory):
                self.send_error(addr, 2, "Access violation")
                return
            if not os.path.isfile(safe_path):
                self.send_error(addr, 1, "File not found")
                return
            # Serve the file using a new ephemeral socket bound to OS-chosen port
            with open(safe_path, "rb") as f:
                block_num = 1
                while True:
                    chunk = f.read(self.BLOCK_SIZE)
                    data_pkt = struct.pack("!HH", self.OP_DATA, block_num) + chunk
                    # send to client (use new socket for transfer)
                    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        tx.sendto(data_pkt, addr)
                        # wait for ACK (with timeout)
                        tx.settimeout(5.0)
                        try:
                            ack, _ = tx.recvfrom(4)
                            if len(ack) < 4:
                                logging.warning("Short ACK received")
                                break
                            ack_opcode, ack_block = struct.unpack("!HH", ack[:4])
                            if ack_opcode != self.OP_ACK or ack_block != block_num:
                                logging.warning("Unexpected ACK %s %s", ack_opcode, ack_block)
                                break
                        except socket.timeout:
                            logging.warning("Timeout waiting for ACK; aborting transfer to %s", addr)
                            break
                    finally:
                        tx.close()
                    if len(chunk) < self.BLOCK_SIZE:
                        # last block
                        break
                    block_num = (block_num + 1) % 65536
            logging.info("Completed TFTP transfer %s -> %s:%d", filename, addr[0], addr[1])
        except Exception as e:
            logging.exception("Error handling TFTP request: %s", e)
            self.send_error(addr, 0, "Server error")

    def send_error(self, addr, code: int, message: str):
        pkt = struct.pack("!H", self.OP_ERROR) + struct.pack("!H", code) + message.encode("utf-8") + b'\x00'
        self.sock.sendto(pkt, addr)


def main():
    parser = argparse.ArgumentParser(description="Serve boot-artifacts over HTTP and TFTP")
    parser.add_argument("--dir", "-d", default="./boot-artifacts", help="Directory to serve")
    parser.add_argument("--http-port", type=int, default=8080, help="HTTP server port")
    parser.add_argument("--tftp-port", type=int, default=6969, help="TFTP server port (use 69 with root)")
    parser.add_argument("--no-http", action="store_true", help="Disable HTTP server")
    parser.add_argument("--no-tftp", action="store_true", help="Disable TFTP server")
    args = parser.parse_args()

    serve_dir = os.path.abspath(args.dir)
    if not os.path.isdir(serve_dir):
        logging.error("Directory does not exist: %s", serve_dir)
        sys.exit(2)

    threads = []
    if not args.no_http:
        t = threading.Thread(target=start_http_server, args=(serve_dir, args.http_port), daemon=True)
        threads.append(t)
        t.start()
    if not args.no_tftp:
        try:
            tftp = TFTPServer(directory=serve_dir, host="0.0.0.0", port=args.tftp_port)
        except PermissionError:
            logging.error("Permission denied binding TFTP port %d; try a higher port or run as root", args.tftp_port)
            sys.exit(2)
        t = threading.Thread(target=tftp.serve_forever, daemon=True)
        threads.append(t)
        t.start()

    # Wait for threads
    try:
        while True:
            for t in threads:
                if not t.is_alive():
                    logging.info("A server thread stopped; exiting")
                    sys.exit(0)
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        logging.info("Shutting down servers")


if __name__ == "__main__":
    main()
