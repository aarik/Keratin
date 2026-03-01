"""
Full roster of Rhino MCP commands available to the LLM on every run.
Single source of truth: add new commands here and in rhino_script.execute_command.

To match Rhino 7 fully: use list_rhino_commands() for MCP tools and list_rhinoscript_functions()
for the full RhinoScriptSyntax (rs.*) API; then look_up_RhinoScriptSyntax(name) and execute_rhino_code().
"""

# Map MCP command type -> RhinoScriptSyntax function name(s) for alignment with Rhino 7.
# Commands that wrap a single rs function are listed here so the LLM can see the match.
MCP_TO_RS_MAP = {
    "trim_curve": "TrimCurve",
    "join_curves": "JoinCurves",
    "curve_domain": None,
    "trim_curve_by_fraction": "TrimCurve",
    "offset_curve": "OffsetCurve",
    "pipe": "AddPipe",
    "create_layer": "AddLayer",
    "delete_layer": "DeleteLayer",
    "get_or_set_current_layer": "CurrentLayer",
    "delete_object": "DeleteObject",
    "boolean_union": "BooleanUnion",
    "boolean_difference": "BooleanDifference",
    "boolean_intersection": "BooleanIntersection",
    "loft": "AddLoftSrf",
    "extrude_curve": "ExtrudeCurve",
    "sweep1": "AddSweep1",
}

# Every command type with a short description for LLM discovery.
# Order: scene/document, layers, objects, geometry, curves, jewelry, Grasshopper, meta.
RHINO_COMMAND_ROSTER = [
    # Scene and document
    ("get_rhino_scene_info", "Basic scene overview: units, layers, sample objects."),
    ("get_document_summary", "Compact document summary: units, layers, object counts."),
    ("get_rhino_layers", "List all layers in the document."),
    ("get_rhino_objects_with_metadata", "Objects with metadata; filter by layer, name, short_id."),
    ("get_rhino_selected_objects", "Get IDs of currently selected objects."),
    ("capture_rhino_viewport", "Capture viewport as image; optional layer and annotations."),
    # Objects and selection
    ("get_objects", "List objects with optional filters (layer, name, type, selected_only)."),
    ("get_object_info", "Detailed info for one object by GUID."),
    ("get_selected_objects_info", "Info for all currently selected objects."),
    ("create_object", "Create point, line, polyline, circle, rectangle, box, sphere, cylinder."),
    ("delete_object", "Delete object by GUID."),
    ("modify_object", "Transform (move, scale, rotate) and set attributes."),
    ("select_objects", "Select by filters; mode: replace, add, subtract."),
    ("add_rhino_object_metadata", "Add name and description to an object for later filtering."),
    # Layers
    ("create_layer", "Create a layer; optional parent and color."),
    ("delete_layer", "Delete layer by name; optional purge."),
    ("get_or_set_current_layer", "Get current layer or set it by name."),
    # Geometry (surfaces / breps)
    ("boolean_union", "Union of multiple breps."),
    ("boolean_difference", "Subtract cutter breps from base."),
    ("boolean_intersection", "Intersection of multiple breps."),
    ("loft", "Loft through curve IDs; optional closed."),
    ("extrude_curve", "Extrude curve along direction; optional cap."),
    ("sweep1", "Sweep shape curves along rail."),
    ("offset_curve", "Offset curve by distance in plane."),
    ("pipe", "Create pipe (solid) along curve with radius and cap."),
    # Curves
    ("trim_curve", "Trim curve to a parameter interval [t0, t1] to keep; optional delete input."),
    ("join_curves", "Join multiple curves into one or more curves; optional delete input and tolerance."),
    # Jewelry helpers
    ("ring_blank", "Create ring blank solid (inner diameter, band width/thickness)."),
    ("head_blank", "Create head blank solid (shape, length/width/height, optional corner radius)."),
    ("section_profile", "Create section profile curve for lofting (center, width, height, plane, shape)."),
    ("place_head_on_band", "Place head blank relative to ring blank using bbox."),
    ("edge_selector_presets", "Get edge indices for presets: outer_band_edges, inner_band_edges, etc."),
    ("safe_boolean_union", "Boolean union with pairwise fallback on failure."),
    ("safe_boolean_difference", "Boolean difference with sequential fallback."),
    ("loft_sections", "Loft between section curves; optional cap."),
    # Code execution
    ("execute_rhinoscript_python_code", "Execute IronPython code in Rhino (no f-strings)."),
    ("execute_code", "Same as execute_rhinoscript_python_code."),
    # Grasshopper
    ("grasshopper_add_components", "Add components to Grasshopper canvas."),
    ("grasshopper_get_definition_info", "Get Grasshopper definition info."),
    ("grasshopper_run_solver", "Run Grasshopper solver."),
    ("grasshopper_clear_canvas", "Clear Grasshopper canvas."),
    ("grasshopper_list_available_components", "List available Grasshopper components."),
    # Discovery (full Rhino 7 API)
    ("list_rhino_commands", "Full roster of MCP commands; includes rs_function when mapped to Rhino 7."),
    ("list_rhinoscript_functions", "Full Rhino 7 RhinoScriptSyntax (rs.*) API: all function names by category."),
    # Legacy / internal
    ("_rhino_create_cube", "Internal: create cube."),
]


def get_full_roster():
    """Return the full roster as a list of dicts for JSON serialization.
    Includes rs_function when the MCP command maps to a RhinoScriptSyntax function."""
    out = []
    for t, d in RHINO_COMMAND_ROSTER:
        entry = {"type": t, "description": d}
        if t in MCP_TO_RS_MAP:
            entry["rs_function"] = MCP_TO_RS_MAP[t]
        out.append(entry)
    return out


def get_roster_text():
    """Return a plain-text summary for the LLM (one line per command)."""
    lines = []
    for t, d in RHINO_COMMAND_ROSTER:
        if not t.startswith("_"):
            lines.append("{0}: {1}".format(t, d))
    return "\n".join(lines)
