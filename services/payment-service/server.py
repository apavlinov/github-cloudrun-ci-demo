"""Tiny payment HTTP service (staging demo); no third-party dependencies."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

from shared.contracts import health_payload

SERVICE = "payment-service"


def response(path: str) -> tuple[int, dict[str, str]]:
    route = urlsplit(path).path
    if route == "/health":
        return 200, health_payload(SERVICE)
    if route == "/version":
        return 200, {"service": SERVICE, "commit": os.getenv("GIT_SHA", "local")}
    return 404, {"error": "not_found"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status, payload = response(self.path)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Handler).serve_forever()
