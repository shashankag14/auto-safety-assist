"""
Local dev server for the recall-radar kanban board.
Serves kanban-board.html and persists ticket state to kanban-data.json
so edits (ticket moves, hours logged, new tickets) survive restarts —
see the fetch("/api/tickets", ...) calls in kanban-board.html.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).parent
HTML_PATH = ROOT / "kanban-board.html"
DATA_PATH = ROOT / "kanban-data.json"
PORT = 8420


class KanbanHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/kanban-board.html"):
            self._serve_html()
        elif self.path == "/api/tickets":
            self._serve_data()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/tickets":
            self._save_data()
        else:
            self.send_error(404)

    def _serve_html(self):
        body = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_data(self):
        body = DATA_PATH.read_bytes() if DATA_PATH.exists() else b"null"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _save_data(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        json.loads(raw)  # reject invalid payloads before touching the file
        DATA_PATH.write_bytes(raw)
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        logger.info(format % args)


def main():
    server = HTTPServer(("127.0.0.1", PORT), KanbanHandler)
    logger.info(f"Kanban board running at http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
