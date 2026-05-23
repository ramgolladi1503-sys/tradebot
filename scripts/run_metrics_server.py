from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.observability import ObservabilityMetricsRegistry, build_default_metrics_registry

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 9108


class MetricsRequestHandler(BaseHTTPRequestHandler):
    registry: ObservabilityMetricsRegistry = build_default_metrics_registry()

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler API.
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found\n")
            return
        body = self.registry.render_prometheus().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def build_server(
    *,
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    registry: ObservabilityMetricsRegistry | None = None,
) -> ThreadingHTTPServer:
    handler = type("TradebotMetricsRequestHandler", (MetricsRequestHandler,), {})
    handler.registry = registry or build_default_metrics_registry()
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve Tradebot observability metrics.")
    parser.add_argument("--host", default=_DEFAULT_HOST)
    parser.add_argument("--port", default=_DEFAULT_PORT, type=int)
    args = parser.parse_args()
    server = build_server(host=args.host, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
