# keratin

**Connect Claude AI to Rhinoceros 3D.**

keratin is a [Model Context Protocol](https://modelcontextprotocol.io) bridge for **Rhino 7**. It lets Claude create geometry, manage layers, run boolean operations, drive Grasshopper, and execute arbitrary RhinoScript — all from a conversation.

---

## How it works

keratin has two components that communicate over a local TCP socket:

```
Claude ──MCP──▶ keratin (Python 3.10+)  ──TCP:9876──▶  rhino_script.py (Rhino 7, IronPython 2.7)
```

| Component | Runtime | Role |
|-----------|---------|------|
| `rhino_script.py` | IronPython 2.7 inside Rhino | Listens on `localhost:9876`, executes commands on Rhino's UI thread |
| `keratin` (MCP server) | Python 3.10+ on the host | Exposes 40+ tools to Claude via the Model Context Protocol |

---

## Installation

### 1. Rhino-side script (Rhino Package Manager)

In Rhino: **Tools > Package Manager** > search **keratin** > Install > Restart Rhino.

### 2. MCP server (pip)

```bash
pip install keratin
```

### 3. Configure your MCP client

**Claude Desktop** — add to `claude_desktop_config.json`:

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

### 4. Load the listener in Rhino

Run `RunPythonScript` and select the installed `rhino_script.py`.

**Auto-start on launch (optional):**
Tools > Options > General > Startup Commands > add:

```
RunPythonScript "C:\path\to\rhino_script.py"
```

---

## Tools

| Category | Tools |
|----------|-------|
| **Scene** | `get_document_summary` `get_rhino_scene_info` `get_rhino_layers` `capture_rhino_viewport` |
| **Objects** | `get_objects` `get_object_info` `create_object` `modify_object` `delete_object` `select_objects` `add_rhino_object_metadata` `get_rhino_objects_with_metadata` `get_rhino_selected_objects` `get_selected_objects_info` |
| **Layers** | `create_layer` `delete_layer` `get_or_set_current_layer` |
| **Geometry** | `boolean_union` `boolean_difference` `boolean_intersection` `loft` `extrude_curve` `sweep1` `offset_curve` `pipe` |
| **Curves** | `trim_curve` `join_curves` `curve_domain` `trim_curve_by_fraction` |
| **Jewelry** | `ring_blank` `head_blank` `section_profile` `place_head_on_band` `edge_selector_presets` `safe_boolean_union` `safe_boolean_difference` `loft_sections` |
| **Grasshopper** | `grasshopper_add_components` `grasshopper_get_definition_info` `grasshopper_run_solver` `grasshopper_clear_canvas` `grasshopper_list_available_components` |
| **Code** | `execute_rhino_code` `execute_rhinoscript_python_code` |
| **Discovery** | `list_rhino_commands` `list_rhinoscript_functions` `look_up_RhinoScriptSyntax` |

---

## Requirements

- Rhinoceros 3D **7** (IronPython 2.7)
- Python **3.10+** on the host machine
- Claude Desktop or Claude Code as the MCP client

---

## Web server variant

For HTTP / WebSocket access instead of stdio MCP:

```bash
keratin-web --host localhost --port 8000
```

| Endpoint | Description |
|----------|-------------|
| `POST /rhino/command` | Execute a Rhino command (`{"type": "...", "params": {...}}`) |
| `GET /rhino/scene` | Get current scene info |
| `GET /rhino/strategy` | Get the recommended Rhino creation strategy |
| `WS /rhino/ws` | WebSocket for streaming command execution |

CORS is restricted to `localhost` origins.

---

## Diagnostics

```bash
# Test the Rhino TCP connection
python tools/ops/diagnose_rhino_connection.py

# View recent errors across all logs
python tools/ops/log_manager.py --since-minutes 60 --level ERROR
```

**Log locations:**

| Source | Location |
|--------|----------|
| Rhino listener | `~/AppData/Local/RhinoMCP/logs/` (Windows) or `~/Library/Application Support/RhinoMCP/logs/` (macOS) |
| Server | `./logs/server/` |
| Diagnostics | `./logs/diagnostics/` |

Rhino-side logs auto-rotate at 5 MB.

---

## Building and publishing

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

Requires a McNeel account. Run `yak login` before your first push.

---

## Attribution

keratin builds on:

- [`rhino-mcp`](https://pypi.org/project/reer-rhino-mcp/) by Reer — MIT License
- [`rhinomcp`](https://github.com/jingcheng-chen/rhinomcp) by Jingcheng Chen — Apache License 2.0

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the preserved license texts under `third_party/`.

---

## Disclaimer

Not affiliated with McNeel & Associates. Use at your own risk. Always work on copies of important files.
