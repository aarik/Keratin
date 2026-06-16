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
| `keratin` (MCP server) | Python 3.10+ on the host | Exposes tools to Claude via the Model Context Protocol |

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

**LM Studio / other MCP clients** — add to your `mcp.json`:

```json
{
  "mcpServers": {
    "rhino": {
      "command": "keratin",
      "args": []
    }
  }
}
```

### 4. Start the listener in Rhino

Type `StartKeratin` in the Rhino command line. To stop: `StopKeratin`.

---

## Tools

keratin exposes **160+ tools** covering the full RhinoScriptSyntax API. Popular functions are registered as individual tools for easy discovery; the rest are accessible through category-level tools.

### Dedicated tools

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

### Individual RhinoScript tools (90+)

High-frequency `rs.*` functions exposed as standalone tools for zero-friction use:

| Area | Examples |
|------|----------|
| **Curve creation** | `rs_AddLine` `rs_AddCircle` `rs_AddArc3Pt` `rs_AddEllipse` `rs_AddInterpCurve` `rs_AddNurbsCurve` `rs_AddRectangle` `rs_AddSpiral` `rs_AddPolyline` `rs_AddBlendCurve` `rs_AddFilletCurve` |
| **Curve query** | `rs_CurveLength` `rs_CurveStartPoint` `rs_CurveEndPoint` `rs_CurveMidPoint` `rs_CurveClosestPoint` `rs_CurveDomain` `rs_CurveArea` `rs_CurveTangent` `rs_IsCurve` `rs_IsCurveClosed` |
| **Curve ops** | `rs_DivideCurve` `rs_EvaluateCurve` `rs_OffsetCurve` `rs_JoinCurves` `rs_ExplodeCurves` `rs_SplitCurve` `rs_RebuildCurve` `rs_ReverseCurve` `rs_CloseCurve` |
| **Surface creation** | `rs_AddSphere` `rs_AddCylinder` `rs_AddCone` `rs_AddBox` `rs_AddTorus` `rs_AddPipe` `rs_AddPlanarSrf` `rs_AddLoftSrf` `rs_AddSweep1` `rs_AddSweep2` `rs_AddRevSrf` `rs_AddEdgeSrf` `rs_AddNetworkSrf` `rs_AddPatch` |
| **Surface ops** | `rs_ExtrudeCurveStraight` `rs_CapPlanarHoles` `rs_FilletSurfaces` `rs_OffsetSurface` `rs_JoinSurfaces` `rs_ExplodePolysurfaces` `rs_DuplicateEdgeCurves` `rs_DuplicateSurfaceBorder` `rs_ExtractIsoCurve` |
| **Surface query** | `rs_SurfaceArea` `rs_SurfaceVolume` `rs_SurfaceNormal` `rs_SurfaceDomain` `rs_EvaluateSurface` `rs_BrepClosestPoint` `rs_IsSurface` `rs_IsPolysurface` `rs_IsPolysurfaceClosed` |
| **Object ops** | `rs_CopyObject` `rs_MoveObject` `rs_RotateObject` `rs_ScaleObject` `rs_MirrorObject` `rs_ObjectLayer` `rs_ObjectName` `rs_ObjectColor` `rs_ObjectType` |
| **Selection** | `rs_AllObjects` `rs_ObjectsByLayer` `rs_ObjectsByType` `rs_ObjectsByName` `rs_SelectedObjects` `rs_UnselectAllObjects` `rs_LastCreatedObjects` |
| **Mesh** | `rs_AddMesh` `rs_MeshBooleanUnion` `rs_MeshBooleanDifference` `rs_JoinMeshes` `rs_MeshToNurb` `rs_IsMesh` |
| **Transform** | `rs_XformScale` `rs_XformTranslation` `rs_TransformObject` |
| **View** | `rs_ZoomExtents` `rs_ZoomSelected` `rs_ViewCamera` `rs_CurrentView` `rs_Redraw` `rs_EnableRedraw` |
| **Misc** | `rs_AddPoint` `rs_AddTextDot` `rs_BoundingBox` `rs_Distance` `rs_Angle` `rs_AddLayer` `rs_SetUserText` `rs_GetUserText` `rs_AddGroup` `rs_PlaneFromNormal` `rs_WorldXYPlane` |

### Category catch-all tools (26)

Any `rs.*` function not listed above is still accessible through its category tool. Call these with a function name and arguments:

`rhinoscript_application` · `rhinoscript_block` · `rhinoscript_curve` · `rhinoscript_dimension` · `rhinoscript_document` · `rhinoscript_geometry` · `rhinoscript_grips` · `rhinoscript_group` · `rhinoscript_hatch` · `rhinoscript_layer` · `rhinoscript_light` · `rhinoscript_line` · `rhinoscript_linetype` · `rhinoscript_material` · `rhinoscript_mesh` · `rhinoscript_object` · `rhinoscript_plane` · `rhinoscript_pointvector` · `rhinoscript_selection` · `rhinoscript_surface` · `rhinoscript_toolbar` · `rhinoscript_transformation` · `rhinoscript_userdata` · `rhinoscript_userinterface` · `rhinoscript_utility` · `rhinoscript_view`

Together these cover all **994 functions** in the Rhino 7 RhinoScriptSyntax API.

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
"C:\Program Files\Rhino 7\System\yak.exe" push keratin-0.1.4-any-any.yak
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
