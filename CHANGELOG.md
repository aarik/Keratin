# Changelog

## 0.1.4 — 2026-03-16

### Added
- **160+ MCP tools** — 90+ individual `rs_*` tools for high-frequency RhinoScript functions, plus 26 category-level catch-all tools covering all 994 functions in the Rhino 7 RhinoScriptSyntax API.
- **`StartKeratin` / `StopKeratin` commands** — install via Yak and type the command in Rhino. No more manual script loading.
- **Thread-safe socket handling** — `threading.Lock` serializes all TCP operations between the MCP server and Rhino.
- **Chunked receive** — large responses are read in 64 KB chunks with a 15 MB safety cap instead of a single 14 MB recv call.
- **Log rotation** — Rhino-side logs auto-rotate at 5 MB to prevent disk bloat.
- **Non-blocking selected objects** — `get_selected_objects_info` uses `rs.SelectedObjects()` instead of an interactive picker.
- **Discovery tools** — `list_rhino_commands`, `list_rhinoscript_functions`, and `look_up_RhinoScriptSyntax` for on-the-fly API reference.

### Fixed
- **Structural indentation bug** — 9 functions (`_get_rhino_objects_with_metadata`, `_capture_rhino_viewport`, `_get_rhino_selected_objects`, and all Grasshopper helpers) were accidentally nested inside `_add_rhino_object_metadata`. Moved to module level with IronPython-safe `__get__` bindings.
- **`boolean_intersection`** — now correctly passes two arguments to `rs.BooleanIntersection` instead of a list.
- **`offset_curve`** — added plane support for proper 3D offsets.
- **Dead code** — removed unused `do_work()` inside `idle_handler`.
- **Duplicate `start()` call** — removed redundant server start at module level.
- **CORS** — restricted from `allow_origins=["*"]` to localhost-only.
- **GitHub doc URL** — corrected from `rhino-8.x` to `rhino-7.x` branch.
- **Short IDs** — added milliseconds to prevent collisions under rapid-fire commands.
- **Listen backlog** — increased from 1 to 5 for connection reliability.
- **IronPython 2.7 compliance** — removed all f-strings and modern Python syntax from Rhino-side code.

## 0.1.3 — 2026-03-16

- Patch release for PyPI/Yak version alignment.

## 0.1.2 — 2026-03-15

- Patch release for Yak version alignment.

## 0.1.1 — 2026-03-15

- Initial public release on PyPI and Rhino Package Manager.
