# keratin — Rhino MCP Bridge

Connect Claude AI to Rhinoceros 3D. Create geometry, manage layers, run boolean ops,
and design jewelry — all from a conversation with Claude.

## Installation

**Step 1 — Install this Yak package inside Rhino:**
Tools → Package Manager → search "keratin" → Install → Restart Rhino

**Step 2 — Install the MCP server on your machine:**
```
pip install keratin
```

**Step 3 — Configure your MCP client (Claude Desktop / Claude Code):**
```json
{
  "mcpServers": {
    "rhino": {
      "command": "keratin"
    }
  }
}
```

**Step 4 — Load the listener inside Rhino:**
- Type `RunPythonScript` in the Rhino command line
- Navigate to the installed `rhino_script.py` and run it
- Optional: add to startup via Tools → Options → General → Startup Commands

## Requirements

- Rhinoceros 3D **7** (IronPython 2.7)
- Python 3.10+ on the host machine (for the MCP server)
- Claude Desktop or Claude Code as the MCP client

## What It Can Do

- Create and modify geometry (curves, surfaces, solids, meshes)
- Boolean operations (union, difference, intersection)
- Layer management
- Loft, sweep, extrude, pipe, offset
- Capture viewport screenshots
- Execute arbitrary RhinoScript
- Grasshopper canvas control
- Jewelry-specific tools (ring blanks, head blanks, prong settings)
