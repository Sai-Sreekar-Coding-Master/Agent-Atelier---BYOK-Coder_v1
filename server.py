#!/usr/bin/env python3
"""
AgentArena — Local API Proxy Server
====================================
Run:  python server.py
Open: http://localhost:5001  in your browser

This server:
  1. Serves the AgentArena HTML app (same origin — zero CORS issues)
  2. Transparently proxies API calls to any provider
     (NVIDIA NIM, OpenCode Zen, OpenAI, B.AI, OpenRouter — all work)
  3. Streams SSE responses back to the browser in real time
  4. Uses the requests library — same code pattern as your Colab notebook

Why this works: Python makes server-to-server HTTP calls.
No browser = no CORS enforcement. Your browser talks to localhost
(which sends CORS headers), localhost talks to NVIDIA (no CORS needed).
"""

import http.server
import socketserver
import json
import os
import sys
import subprocess

PORT = 5001
HTML_FILE = "AgentArena-Atelier.html"


def ensure_requests():
    """Make sure the requests library is installed."""
    try:
        import requests
        return requests
    except ImportError:
        print("Installing requests library...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
        import requests
        return requests


requests = ensure_requests()


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Handles: GET (serve HTML + health check), POST (proxy), OPTIONS (CORS preflight)."""

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept, HTTP-Referer")

    # ─── OPTIONS: CORS preflight ───────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ─── GET: serve HTML or health check ───────────────────────────
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            # Serve the app
            try:
                with open(HTML_FILE, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_response(404)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(b"<h1>AgentArena-Atelier.html not found</h1><p>Put this server.py in the same folder as the HTML file.</p>")

        elif self.path == "/health":
            # Health check — the app pings this to detect the proxy
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "proxy": "AgentArena", "port": PORT}).encode())

        else:
            self.send_response(404)
            self._cors_headers()
            self.end_headers()

    # ─── POST: transparent proxy ───────────────────────────────────
    # Path format: /https://integrate.api.nvidia.com/v1/chat/completions
    # The app's proxiedUrl() function produces this format automatically.
    def do_POST(self):
        # Extract the target URL from the path
        target_url = self.path.lstrip("/")

        # Also support /proxy/https://... format
        if target_url.startswith("proxy/"):
            target_url = target_url[6:]

        if not target_url.startswith("http"):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Bad target URL. Expected /https://..."}).encode())
            return

        # Read the request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # Build forwarded headers — pass through Authorization, Content-Type, Accept
        # but replace Host with the target's host
        forward_headers = {}
        for key, val in self.headers.items():
            k = key.lower()
            if k in ("host", "origin", "referer", "content-length", "connection"):
                continue
            forward_headers[key] = val

        # Parse the body to check streaming and inject NVIDIA-specific params
        is_stream = False
        try:
            payload = json.loads(body)
            is_stream = payload.get("stream", False)

            # NVIDIA NIM: auto-inject reasoning_effort and seed if not present
            # (matches the real NVIDIA API code from the user's notebook)
            if "integrate.api.nvidia.com" in target_url:
                if "reasoning_effort" not in payload:
                    payload["reasoning_effort"] = "max"
                if "seed" not in payload:
                    payload["seed"] = 0
                # Ensure max_tokens is high enough for reasoning models
                if payload.get("max_tokens", 0) < 4096:
                    payload["max_tokens"] = 16384
                body = json.dumps(payload).encode()
                # Update Content-Type to be explicit
                forward_headers["Content-Type"] = "application/json"
                forward_headers["Accept"] = "text/event-stream" if is_stream else "application/json"

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Not JSON (e.g. multipart form data) — forward as-is

        try:
            if is_stream:
                # ─── Streaming: forward SSE chunks in real time ───
                response = requests.post(
                    target_url,
                    headers=forward_headers,
                    data=body,
                    stream=True,
                    timeout=120,
                )

                if response.status_code != 200:
                    # Error response — send as JSON
                    error_text = response.text[:500]
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", "application/json")
                    self._cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": f"API {response.status_code}",
                        "detail": error_text,
                    }).encode())
                    return

                # Stream the SSE response back to the browser
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self._cors_headers()
                self.end_headers()

                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            # Browser closed the connection — stop streaming
                            break

            else:
                # ─── Non-streaming: forward and return full response ───
                response = requests.post(
                    target_url,
                    headers=forward_headers,
                    data=body,
                    timeout=120,
                )

                self.send_response(response.status_code)
                ct = response.headers.get("Content-Type", "application/json")
                self.send_header("Content-Type", ct)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(response.content)

        except requests.exceptions.ConnectionError as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Connection failed",
                "detail": f"Could not reach {target_url}. {str(e)[:200]}",
            }).encode())

        except requests.exceptions.Timeout:
            self.send_response(504)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Request timed out (120s)",
                "detail": f"The API at {target_url} did not respond in time.",
            }).encode())

        except requests.exceptions.RequestException as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Proxy error",
                "detail": str(e)[:300],
            }).encode())

    def log_message(self, format, *args):
        """Quiet logging — only show POST requests and errors."""
        if args:
            msg = str(args[0])
            if "POST" in msg or "50" in msg or "40" in msg:
                super().log_message(format, *args)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Handle multiple requests concurrently (needed for streaming)."""
    daemon_threads = True


def main():
    # Check HTML file
    if not os.path.exists(HTML_FILE):
        print(f"\n  !! {HTML_FILE} not found in current directory.")
        print(f"     Put server.py in the same folder as the HTML file.\n")
        sys.exit(1)

    print(f"\n  ╔══════════════════════════════════════════════╗")
    print(f"  ║  AgentArena — Local API Proxy Server         ║")
    print(f"  ╠══════════════════════════════════════════════╣")
    print(f"  ║                                              ║")
    print(f"  ║  App:  http://localhost:{PORT}                 ║")
    print(f"  ║                                              ║")
    print(f"  ║  NVIDIA NIM   →  works (server-side proxy)   ║")
    print(f"  ║  OpenCode Zen →  works (server-side proxy)   ║")
    print(f"  ║  OpenAI       →  works (server-side proxy)   ║")
    print(f"  ║  B.AI         →  works (server-side proxy)   ║")
    print(f"  ║  OpenRouter   →  works (native CORS)         ║")
    print(f"  ║  Ollama       →  works (localhost)           ║")
    print(f"  ║                                              ║")
    print(f"  ║  Press Ctrl+C to stop                        ║")
    print(f"  ╚══════════════════════════════════════════════╝\n")

    with ThreadingHTTPServer(("", PORT), ProxyHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.\n")


if __name__ == "__main__":
    main()
