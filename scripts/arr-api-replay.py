#!/usr/bin/env python3
"""
Stand in for the arrs by replaying saved API responses (from
`scripts/export-arr-config.py --raw-dir DIR`, or saved by hand), so a Configarr
dry run can be checked with no API keys and no access to the real apps.

    python3 scripts/arr-api-replay.py DIR [--port 8765]

GET /<arr>/api and /<arr>/api/{v1,v3}/<endpoint> return DIR/<arr>/<endpoint>.json
(slashes become dashes). Anything else gets a 404 or 405 and is logged loudly:
a 404 means one more endpoint needs saving, and a POST, PUT or DELETE means the
run was not a dry run. See configarr/README.md.
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def make_handler(raw_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parts = urlsplit(self.path).path.strip("/").split("/", 1)
            arr, rest = parts[0], parts[1] if len(parts) > 1 else ""
            endpoint = None
            if rest == "api":
                endpoint = "api"
            elif rest.startswith(("api/v1/", "api/v3/")):
                endpoint = rest[len("api/v3/"):].replace("/", "-")
            path = raw_dir / arr / f"{endpoint}.json" if endpoint else None
            if path is None or not path.is_file():
                print(f"MISSING  GET {self.path}", file=sys.stderr, flush=True)
                self.send_error(404)
                return
            body = path.read_bytes()
            json.loads(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def refuse(self):
            print(f"WRITE    {self.command} {self.path}", file=sys.stderr, flush=True)
            self.send_error(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = refuse

        def log_message(self, fmt, *args):
            print(f"         {self.command} {self.path}", file=sys.stderr, flush=True)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1].strip())
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    # Loopback only: Docker Desktop still reaches it as host.docker.internal.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.raw_dir))
    print(f"replaying {args.raw_dir} on :{args.port}", file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
