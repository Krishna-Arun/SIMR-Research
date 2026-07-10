"""Minimal Python stdio JSON-RPC client for the PubMed MCP server.

Spawns `node build/index.js`, performs the MCP initialize handshake, caches tools/list, and exposes
call(name, args). Newline-delimited JSON-RPC 2.0 over stdio. A background reader thread routes
responses to per-id futures. Crash-resilient: on EOF/timeout the server is respawned and
re-handshaked; persistent failure is surfaced so the caller's circuit breaker can trip.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from concurrent.futures import Future


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, cfg: dict):
        m = cfg["pubmed_mcp"]
        self.node = m["node_bin"]
        self.cwd = m["server_dir"]
        self.entry = m["entry"]
        self.timeout = float(m.get("call_timeout_s", 30))
        self.proc: subprocess.Popen | None = None
        self._futures: dict[int, Future] = {}
        self._next_id = 0
        self._lock = threading.Lock()
        self.tools: list[dict] = []

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self):
        env = dict(os.environ)
        self.proc = subprocess.Popen(
            [self.node, self.entry], cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env,
        )
        threading.Thread(target=self._reader, daemon=True).start()
        self._handshake()
        return self

    def _handshake(self):
        self._request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "qgen", "version": "0.1"}})
        self._notify("notifications/initialized")
        res = self._request("tools/list", {})
        self.tools = res.get("tools", [])

    def restart(self):
        try:
            if self.proc:
                self.proc.kill()
        except Exception:
            pass
        with self._lock:
            self._futures.clear()
        self.start()

    def close(self):
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass

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
                continue
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

    # ── tools ────────────────────────────────────────────────────────────────
    def call(self, name: str, arguments: dict) -> str:
        """Call an MCP tool; return concatenated text content."""
        res = self._request("tools/call", {"name": name, "arguments": arguments})
        parts = []
        for block in res.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        if res.get("isError"):
            raise MCPError(f"tool {name} returned error: {' '.join(parts)[:300]}")
        return "\n".join(parts)


if __name__ == "__main__":
    from qgen.config import load_config
    cli = MCPClient(load_config()).start()
    print("tools:", [t["name"] for t in cli.tools])
    out = cli.call("search_articles", {"query": "vancomycin MRSA bacteremia guideline", "max_results": 2})
    print(out[:500])
    cli.close()
