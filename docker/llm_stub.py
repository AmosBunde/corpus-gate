"""Health-only stand-in for the llama.cpp server at milestone M0.

Milestone M2 replaces this service with the llama.cpp server image
plus the quantized base model; docker-compose.yml documents the swap
next to the service definition.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(
            {"status": "stub", "replaced_in": "M2", "runtime": "llama.cpp server"}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
