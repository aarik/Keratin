# Changelog

## [0.1.0] — 2026-03-10

Initial public release as **keratin**.

### Added
- Full Rhino 7 (IronPython 2.7) compatible listener script (`rhino_script.py`)
- MCP server exposing 40+ tools to Claude via stdio transport (`keratin` CLI)
- Web server variant with HTTP + WebSocket transport (`keratin-web` CLI)
- Scene inspection: document summary, layer listing, object queries, viewport capture
- Object operations: create, modify, delete, select, metadata tagging
- Geometry operations: boolean union/difference/intersection, loft, extrude, sweep, pipe, offset
- Curve operations: trim, join, domain query, fractional trim
- Jewelry-specific tools: ring blank, head blank, section profile, prong placement, edge selector presets, safe booleans, loft sections
- Grasshopper canvas control: add components, run solver, inspect definition
- Code execution: arbitrary IronPython 2.7 code inside Rhino, full RhinoScriptSyntax access
- Discovery tools: list all MCP commands, browse full RhinoScriptSyntax API by category, look up individual function docs
- Newline-delimited JSON (NDJSON) framing over TCP — robust against packet fragmentation
- Rhino-side idle-thread execution pattern — safe main-thread document access
- Diagnostic tools: connection checker, multi-source log viewer
- Yak package (`yak-package/`) for distribution via Rhino's Package Manager
- Third-party attribution in `THIRD_PARTY_NOTICES.md`

### Fixed (vs upstream)
- Removed `#! python3` shebang for IronPython 2.7 compatibility
- Repaired corrupted `stop()` method structure in Rhino-side listener
- Added missing `_curve_domain` and `_trim_curve_by_fraction` handler implementations
- Added missing `join_curves` and `list_rhino_commands` MCP tool method bodies
- Fixed zero-indentation bug in `list_rhinoscript_functions` body

### Attribution
Derived from `rhino-mcp` (MIT, Reer) and `rhinomcp` (Apache 2.0, Jingcheng Chen).
See `THIRD_PARTY_NOTICES.md` for full attribution.
