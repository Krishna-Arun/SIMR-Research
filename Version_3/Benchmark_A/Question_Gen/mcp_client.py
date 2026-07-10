"""
Minimal Python stdio JSON-RPC client for an MCP server.

The Benchmark A generation agents run as local HF models with no native
tool-calling API, so we drive MCP servers ourselves: spawn the server process,
do the MCP initialize handshake, cache tools/list, and expose call(name, args).

Newline-delimited JSON-RPC 2.0 over stdio; a background reader thread routes
responses to per-id futures. Adapted from the Version_2 qgen client, made
self-contained (no config module) with a ready-made PubMed factory.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from concurrent.futures import Future
from pathlib import Path

# PubMed MCP server lives one level up from Question_Gen/.
PUBMED_SERVER_DIR = Path(__file__).resolve().parent.parent / "PubMed-MCP-Server"
PUBMED_ENTRY = PUBMED_SERVER_DIR / "build" / "index.js"


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, server_dir: str | Path, entry: str | Path,
                 node_bin: str = "node", call_timeout_s: float = 30.0):
        self.node = node_bin
        self.cwd = str(server_dir)
        self.entry = str(entry)
        self.timeout = call_timeout_s
        self.proc: subprocess.Popen | None = None
        self._futures: dict[int, Future] = {}
        self._next_id = 0
        self._lock = threading.Lock()
        self.tools: list[dict] = []

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> "MCPClient":
        if not Path(self.entry).exists():
            raise MCPError(
                f"server entry not found: {self.entry}\n"
                f"Build it first: (cd {self.cwd} && npm install && npm run build)")
        self.proc = subprocess.Popen(
            [self.node, self.entry], cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=dict(os.environ),
        )
        threading.Thread(target=self._reader, daemon=True).start()
        self._handshake()
        return self

    def _handshake(self):
        self._request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "benchmark-a-qgen", "version": "0.1"}})
        self._notify("notifications/initialized")
        self.tools = self._request("tools/list", {}).get("tools", [])

    def close(self):
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    # ── io ───────────────────────────────────────────────────────────────────
    def _reader(self):
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue          # server may log non-JSON to stdout; ignore
            mid = msg.get("id")
            if mid is None:
                continue
            with self._lock:
                fut = self._futures.pop(mid, None)
            if fut and not fut.done():
                fut.set_result(msg)

    def _send(self, payload: dict):
        assert self.proc and self.proc.stdin
        with self._lock:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()

    def _notify(self, method: str, params: dict | None = None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._next_id += 1
            mid = self._next_id
            fut: Future = Future()
            self._futures[mid] = fut
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        try:
            msg = fut.result(timeout=self.timeout)
        except Exception as e:
            raise MCPError(f"{method} timed out/failed: {e}")
        if "error" in msg:
            raise MCPError(f"{method} error: {msg['error']}")
        return msg.get("result", {})

    # ── tools ──────────────────────────────────────────────────────────────��─
    def call(self, name: str, arguments: dict) -> str:
        """Call an MCP tool; return its concatenated text content."""
        res = self._request("tools/call", {"name": name, "arguments": arguments})
        parts = [b.get("text", "") for b in res.get("content", [])
                 if isinstance(b, dict) and b.get("type") == "text"]
        if res.get("isError"):
            raise MCPError(f"tool {name} error: {' '.join(parts)[:300]}")
        return "\n".join(parts)


def pubmed_client(**kwargs) -> MCPClient:
    """Factory for the bundled PubMed MCP server."""
    return MCPClient(PUBMED_SERVER_DIR, PUBMED_ENTRY, **kwargs)


if __name__ == "__main__":
    # Smoke test: handshake, list tools, run one search. Needs the server built
    # and network access to NCBI (set NCBI_API_KEY / NCBI_EMAIL to raise limits).
    with pubmed_client() as cli:
        print("tools:", [t["name"] for t in cli.tools])
        out = cli.call("search_articles",
                       {"query": "vancomycin MRSA bacteremia guideline", "max_results": 2})
        print(out[:600])
