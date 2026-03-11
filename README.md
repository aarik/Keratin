# keratin

**Connect Claude AI to Rhinoceros 3D.**

keratin is a [Model Context Protocol](https://modelcontextprotocol.io) bridge for **Rhino 7**. It lets Claude create geometry, manage layers, run boolean operations, drive Grasshopper, and execute arbitrary RhinoScript — all from a conversation.

> Part of the **lineforge** tool family.

---

## How it works

keratin is two components that talk to each other over a local TCP socket:

```
Claude ──MCP──▶ keratin (host, Python 3)  ──TCP:9876──▶  rhino_script.py (Rhino, IronPython 2.7)
```

1. **`rhino_script.py`** runs inside Rhino as an IronPython script. It listens for commands and executes them safely on Rhino's main thread.
2. **`keratin`** (the MCP server) runs on your machine and exposes 40+ tools to Claude via the Model Context Protocol.

---

## Installation

### Step 1 — Rhino-side script (via Rhino Package Manager)

In Rhino: **Tools → Package Manager** → search **keratin** → Install → Restart Rhino

### Step 2 — MCP server (via pip)

```bash
pip install keratin
```

### Step 3 — Configure your MCP client

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "rhino": {
      "command": "keratin"
    }
  }
}
```

**Claude Code:**
```bash
claude mcp add rhino -- keratin
```

### Step 4 — Load the listener in Rhino

In Rhino, run `RunPythonScript` and select the installed `rhino_script.py`.

**Optional — auto-start on Rhino launch:**
Tools → Options → General → Startup Commands → add:
```
RunPythonScript "C:\path\to\rhino_script.py"
```

---

## Tool surface

| Category | Tools |
|----------|-------|
| **Scene** | `get_document_summary`, `get_rhino_scene_info`, `get_rhino_layers`, `capture_rhino_viewport` |
| **Objects** | `get_objects`, `get_object_info`, `create_object`, `modify_object`, `delete_object`, `select_objects`, `add_rhino_object_metadata`, `get_rhino_objects_with_metadata`, `get_rhino_selected_objects` |
| **Layers** | `create_layer`, `delete_layer`, `get_or_set_current_layer` |
| **Geometry** | `boolean_union`, `boolean_difference`, `boolean_intersection`, `loft`, `extrude_curve`, `sweep1`, `offset_curve`, `pipe` |
| **Curves** | `trim_curve`, `join_curves`, `curve_domain`, `trim_curve_by_fraction` |
| **Jewelry** | `ring_blank`, `head_blank`, `section_profile`, `place_head_on_band`, `edge_selector_presets`, `safe_boolean_union`, `safe_boolean_difference`, `loft_sections` |
| **Grasshopper** | `grasshopper_add_components`, `grasshopper_get_definition_info`, `grasshopper_run_solver`, `grasshopper_clear_canvas`, `grasshopper_list_available_components` |
| **Code execution** | `execute_rhinoscript_python_code`, `execute_rhino_code` |
| **Discovery** | `list_rhino_commands`, `list_rhinoscript_functions`, `look_up_RhinoScriptSyntax` |

---

## Requirements

- Rhinoceros 3D **7** (IronPython 2.7)
- Python 3.10+ on the host machine
- Claude Desktop or Claude Code as the MCP client

---

## Web server variant

For HTTP/WebSocket access instead of stdio:

```bash
keratin-web --host localhost --port 8000
```

Endpoints: `POST /rhino/command`, `GET /rhino/scene`, `WS /ws`

---

## Diagnostics

```bash
# Check the Rhino TCP connection
python tools/ops/diagnose_rhino_connection.py

# View recent errors across all logs
python tools/ops/log_manager.py --since-minutes 60 --level ERROR
```

Logs are written to `./logs/` (server / rhino / diagnostics).

---

## Building & publishing

**PyPI (MCP server):**
```bash
python -m build
python -m twine upload dist/*
```

**Yak (Rhino Package Manager):**
```bash
cd yak-package
"C:\Program Files\Rhino 7\System\yak.exe" build
"C:\Program Files\Rhino 7\System\yak.exe" push keratin-0.1.0-any-any.yak
```

> Requires a McNeel account. Run `yak login` before your first push.

---

## Attribution

keratin is built on the shoulders of:

- [`rhino-mcp`](https://pypi.org/project/reer-rhino-mcp/) by Reer — MIT License
- [`rhinomcp`](https://github.com/jingcheng-chen/rhinomcp) by Jingcheng Chen — Apache License 2.0

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the preserved license texts under `third_party/`.

---

## Disclaimer

Not affiliated with McNeel & Associates. Use at your own risk. Always work on copies of important files.
