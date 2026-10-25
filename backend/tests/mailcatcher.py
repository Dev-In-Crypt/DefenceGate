"""A local SMTP server for tests (WP-123): enough of RFC 5321 for smtplib's NOOP, MAIL, RCPT and
DATA, on 127.0.0.1 and a free port, keeping what it receives in a list. No network beyond the
loopback, no TLS (the mailer accepts plain SMTP only to a relay on this host)."""

from __future__ import annotations

import socketserver
import threading
from email import message_from_bytes, policy


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        box: list = self.server.box            # type: ignore[attr-defined]
        self.wfile.write(b"220 catcher ready\r\n")
        rcpt: list[str] = []
        while line := self.rfile.readline():
            cmd = line.strip().upper()
            if cmd.startswith((b"EHLO", b"HELO")):
                self.wfile.write(b"250 catcher\r\n")
            elif cmd.startswith(b"MAIL FROM"):
                rcpt = []
                self.wfile.write(b"250 ok\r\n")
            elif cmd.startswith(b"RCPT TO"):
                rcpt.append(line.decode().split(":", 1)[1].strip().strip("<>"))
                self.wfile.write(b"250 ok\r\n")
            elif cmd == b"DATA":
                self.wfile.write(b"354 go on\r\n")
                data = b""
                while (chunk := self.rfile.readline()) not in (b".\r\n", b""):
                    data += chunk[1:] if chunk.startswith(b"..") else chunk
                box.append({"rcpt": rcpt, "message": message_from_bytes(data, policy=policy.default)})
                self.wfile.write(b"250 queued\r\n")
            elif cmd == b"QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:                               # NOOP, RSET
                self.wfile.write(b"250 ok\r\n")


class MailCatcher:
    """`with MailCatcher() as smtp:` then `smtp.port` and `smtp.box`."""

    def __init__(self) -> None:
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.server.box = []                    # type: ignore[attr-defined]
        self.port = self.server.server_address[1]
        self.box: list = self.server.box        # type: ignore[attr-defined]

    def __enter__(self) -> "MailCatcher":
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
