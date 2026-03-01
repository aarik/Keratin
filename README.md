# Rhino MCP Extended (Rhino 7, stability-first)

A stability-focused MCP (Model Context Protocol) server for **Rhino 7**, based on the proven execution approach from `rhino-mcp`, with an expanded tool surface inspired by `rhinomcp`.

This project exists for one reason: **more capability without Rhino falling over**.

## What this is

- A Python MCP server + a Rhino-side Python script that lets an AI agent inspect and manipulate a Rhino document.
- Designed primarily for **Rhino 7 (IronPython)**.

## What’s different from upstream

This project is an adapted integration:

- Keeps Rhino operations on the safe execution path (main-thread / Idle execution).
- Uses **newline-delimited JSON** over TCP so messages don’t randomly corrupt when TCP splits/joins packets.
- Adds additional tools for:
  - document inspection
  - object/layer operations
  - common geometry operations (including basic booleans)

## How it works

1. You run `rhino_script.py` inside Rhino 7.  
   It opens a local TCP listener and executes requests safely inside Rhino.
2. You run the MCP server (`main.py`).  
   It exposes MCP tools to your client (Claude Desktop, custom MCP client, etc).

## Quick start

### 1) Start the Rhino side

- In Rhino 7: run the Python script `rhino_script.py` (EditPythonScript → Run).

### 2) Start the MCP server

```bash
python main.py
```

> Note: Rhino-side and server-side must be kept in sync.  
> This project uses newline-delimited JSON framing, so don’t mix “old server + new script” or vice versa.

## Tool surface (high level)

- Document + object inspection (scene summary, object lists, object info)
- Layer operations (create/delete/set current)
- Object operations (create/modify/delete/select)
- History (undo/redo)
- Geometry (loft/extrude/sweep/offset/pipe, boolean union/diff/intersection)

Exact tool names are defined in `rhino_mcp/rhino_tools.py`.

## Attribution and licenses

This project is derived from / inspired by upstream open-source work.  
See `THIRD_PARTY_NOTICES.md` and the preserved license texts under `third_party/`.

- `rhino-mcp` — MIT License
- `rhinomcp` — Apache License 2.0

## Disclaimer

Not affiliated with McNeel & Associates. Use at your own risk. Always test on copies of files.


## Diagnostics and log viewing

- Run `python tools/ops/diagnose_rhino_connection.py` to sanity-check the Rhino socket connection.
- Run `python tools/ops/log_manager.py --since-minutes 60 --level ERROR` to view recent errors across logs.

Logs are stored under `./logs/` (server / rhino / diagnostics).
