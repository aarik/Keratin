#!/usr/bin/env python3
"""
Rhino MCP Extended - Connection Diagnostic

What it does:
- Opens a TCP connection to the Rhino-side socket server (default localhost:9876)
- Sends a couple of safe test commands using newline-delimited JSON
- Prints a clear pass/fail summary
- Writes a timestamped log under ./logs/diagnostics/

This script is intentionally dependency-free.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876
RECV_CHUNK = 65536


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _setup_logging(verbose: bool) -> Path:
    root = _project_root()
    log_dir = root / "logs" / "diagnostics"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = log_dir / f"rhino_diagnostic_{ts}.log"

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] [diagnostic] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, encoding="utf-8")],
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    return log_file


def _recv_line(sock: socket.socket, timeout_s: float) -> bytes:
    sock.settimeout(timeout_s)
    buf = b""
    start = time.time()

    while True:
        if b"\n" in buf:
            line, _, rest = buf.partition(b"\n")
            # keep rest in socket buffer? can't. So we only read one response per request here.
            return line

        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for response line after {timeout_s:.1f}s")

        chunk = sock.recv(RECV_CHUNK)
        if not chunk:
            raise ConnectionError("Socket closed while waiting for response")
        buf += chunk


def send_command(host: str, port: int, command_type: str, params: Optional[Dict[str, Any]] = None,
                 timeout_s: float = 10.0) -> Dict[str, Any]:
    """
    Send a newline-delimited JSON command and parse the newline-delimited JSON response.
    """
    logger = logging.getLogger(__name__)
    params = params or {}

    payload = {
        "id": f"diag_{int(time.time() * 1000)}",
        "type": command_type,
        "params": params,
    }
    wire = (json.dumps(payload) + "\n").encode("utf-8")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        logger.info(f"Connecting to {host}:{port} ...")
        s.connect((host, port))
        logger.info("Connected")

        logger.info(f"Sending: {payload}")
        s.sendall(wire)

        raw = _recv_line(s, timeout_s=timeout_s)
        logger.info(f"Raw response: {raw[:5000]!r}" + (" ...truncated" if len(raw) > 5000 else ""))

        try:
            resp = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            return {"success": False, "error": f"Failed to parse JSON response: {e}", "raw": raw.decode("utf-8", errors="replace")}

        # Normalize a few common shapes
        if isinstance(resp, dict):
            if resp.get("status") == "error":
                return {"success": False, "error": resp.get("message", "Unknown error"), "response": resp}
            if "error" in resp:
                return {"success": False, "error": resp.get("error", "Unknown error"), "response": resp}
        return {"success": True, "response": resp}
    finally:
        try:
            s.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnose Rhino MCP Extended socket connectivity.")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    log_file = _setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    print("\n" + "=" * 60)
    print(" Rhino MCP Extended - Connection Diagnostic")
    print("=" * 60)
    print(f"Logging to: {log_file}\n")

    # 1) Basic TCP connect test
    tcp_ok = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((args.host, args.port))
        s.close()
        tcp_ok = True
        print(f"✅ TCP connect OK ({args.host}:{args.port})")
        logger.info("TCP connect test: SUCCESS")
    except Exception as e:
        print(f"❌ TCP connect FAILED ({args.host}:{args.port}): {e}")
        logger.error("TCP connect test: FAILED")
        logger.error(traceback.format_exc())
        print("\nIf Rhino is running, make sure you executed rhino_script.py and it is listening on the same port.")
        return 1

    # 2) Safe command: get_rhino_scene_info (exists in rhino-mcp and should remain)
    scene = send_command(args.host, args.port, "get_rhino_scene_info", {}, timeout_s=args.timeout)
    scene_ok = scene.get("success", False)
    print(f"{'✅' if scene_ok else '❌'} get_rhino_scene_info")

    # 3) Safe-ish command: get_document_summary (optional, only if present)
    summary = send_command(args.host, args.port, "get_document_summary", {}, timeout_s=args.timeout)
    summary_ok = summary.get("success", False)
    print(f"{'✅' if summary_ok else '⚠️'} get_document_summary (optional)")

    # 4) Optional: create a tiny test point if supported (disabled by default)
    # Keeping this script non-invasive by default.

    print("\n" + "-" * 60)
    print("Summary")
    print("-" * 60)
    print(f"TCP: {'OK' if tcp_ok else 'FAIL'}")
    print(f"get_rhino_scene_info: {'OK' if scene_ok else 'FAIL'}")
    print(f"get_document_summary: {'OK' if summary_ok else 'NOT AVAILABLE / FAIL'}")

    if not scene_ok:
        print("\nMost likely causes:")
        print("- Rhino-side script not running or wrong port")
        print("- Protocol mismatch (newline framing expected)")
        print("- Another service is already bound to that port")
        return 2

    print("\n✅ Diagnostic looks good.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Unhandled error: {e}")
        logging.getLogger(__name__).error(traceback.format_exc())
        raise
