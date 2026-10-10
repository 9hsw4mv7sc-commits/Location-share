import os
import json
import secrets
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
TOKEN = os.environ.get("ADMIN_TOKEN", "")
DATA_FILE = BASE / "submissions.jsonl"

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            content = (BASE / "index.html").read_text(encoding="utf-8")
            self._send(200, content, "text/html; charset=utf-8")
        elif path == "/admin":
            provided = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not TOKEN or not secrets.compare_digest(provided, TOKEN):
                self._send(401, '{"error":"Unauthorized"}')
                return
            if not DATA_FILE.exists():
                self._send(200, "[]")
                return
            rows = []
            for line in DATA_FILE.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            self._send(200, json.dumps(rows, ensure_ascii=False))
        else:
            self._send(404, '{"error":"Not found"}')

    def do_POST(self):
        if urlparse(self.path).path != "/api/location":
            self._send(404, '{"error":"Not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ValueError("Invalid body size")
            obj = json.loads(self.rfile.read(length))
            lat = float(obj["latitude"])
            lon = float(obj["longitude"])
            accuracy = float(obj["accuracy_m"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= accuracy <= 1_000_000):
                raise ValueError("Invalid coordinates")
            record = {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "latitude": lat,
                "longitude": lon,
                "accuracy_m": accuracy,
                "device_timestamp": str(obj.get("timestamp", ""))[:64]
            }
            with DATA_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._send(201, '{"ok":true}')
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._send(400, '{"error":"Invalid data"}')

    def log_message(self, fmt, *args):
        # Do not log request details or client IPs.
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Listening on port {port}; configure HTTPS at your hosting provider.")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
