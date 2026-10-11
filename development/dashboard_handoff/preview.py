from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
ALLOWED = {"/", "/index.html", "/app.js", "/styles.css", "/snapshot.json"}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] not in ALLOWED:
            self.send_error(404, "Not found")
            return
        super().do_GET()

    def translate_path(self, path):
        clean = path.split("?", 1)[0]
        if clean not in ALLOWED:
            return os.devnull
        return str(ROOT / ("index.html" if clean == "/" else clean.lstrip("/")))

    def log_message(self, format, *args):
        print(format % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8099), Handler)
    print("Preview: http://127.0.0.1:8099/")
    server.serve_forever()
