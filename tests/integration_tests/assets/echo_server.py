#!/usr/bin/env python3
"""
Very simple HTTP daemon server in python for incoming POST data to stdout.
Each line represents a request's POST data a dictionary.
"""
import contextlib
import pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer

OUTFILE = pathlib.Path("/var/tmp/echo_server_output")


class Server(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        self._set_response()

    def do_POST(self):
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length).decode("utf-8")
        with OUTFILE.open("a") as f:
            f.write(f"{post_data}\n")
        self._set_response()

    def log_message(self, *args, **kwargs):
        pass


server_address = ("", 55555)
httpd = HTTPServer(server_address, Server)
with contextlib.suppress(KeyboardInterrupt):
    httpd.serve_forever()
httpd.server_close()
