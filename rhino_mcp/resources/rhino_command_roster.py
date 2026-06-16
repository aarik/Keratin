"""
Full roster of Rhino MCP commands available to the LLM on every run.
Single source of truth: add new commands here and in rhino_script.execute_command.

Tool surface overview:
  - ~43 original dedicated tools (scene, objects, layers, geometry, jewelry, Grasshopper)
  - ~90 individual rs_* tools for the most-used RhinoScriptSyntax functions
  - 26 category-level rhinoscript_<category> catch-all tools covering every remaining rs.* function
  - Discovery tools: list_rhino_commands, list_rhinoscript_functions, look_up_RhinoScriptSyntax
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
# Order: scene/document, layers, objects, geometry, curves, jewelry, Grasshopper,
#         individual rs_* tools, category catch-alls, meta.
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
    ("curve_domain", "Get the parameter domain [t0, t1] of a curve."),
    ("trim_curve_by_fraction", "Trim curve using fractional parameters [0..1] mapped over its domain."),
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

    # --- Individual rs_* tools (high-frequency RhinoScriptSyntax functions) ---
    # Curve creation
    ("rs_AddLine", "rs.AddLine: add line between two points."),
    ("rs_AddPolyline", "rs.AddPolyline: add polyline through points."),
    ("rs_AddCircle", "rs.AddCircle: add circle from center and radius."),
    ("rs_AddArc3Pt", "rs.AddArc3Pt: add arc through three points."),
    ("rs_AddEllipse", "rs.AddEllipse: add ellipse from plane and radii."),
    ("rs_AddInterpCurve", "rs.AddInterpCurve: interpolated curve through points."),
    ("rs_AddNurbsCurve", "rs.AddNurbsCurve: NURBS curve from control points/knots."),
    ("rs_AddRectangle", "rs.AddRectangle: rectangular polyline from plane, width, height."),
    ("rs_AddSpiral", "rs.AddSpiral: spiral curve."),
    ("rs_AddBlendCurve", "rs.AddBlendCurve: blend curve between two curves."),
    ("rs_AddFilletCurve", "rs.AddFilletCurve: fillet between two curves."),
    # Curve query
    ("rs_CurveLength", "rs.CurveLength: length of a curve."),
    ("rs_CurveStartPoint", "rs.CurveStartPoint: start point of curve."),
    ("rs_CurveEndPoint", "rs.CurveEndPoint: end point of curve."),
    ("rs_CurveMidPoint", "rs.CurveMidPoint: midpoint of curve."),
    ("rs_CurveClosestPoint", "rs.CurveClosestPoint: closest parameter on curve to point."),
    ("rs_CurveDomain", "rs.CurveDomain: parameter domain [t0, t1]."),
    ("rs_CurveArea", "rs.CurveArea: area of closed planar curve."),
    ("rs_CurveTangent", "rs.CurveTangent: tangent vector at parameter."),
    ("rs_IsCurve", "rs.IsCurve: test if object is a curve."),
    ("rs_IsCurveClosed", "rs.IsCurveClosed: test if curve is closed."),
    # Curve operations
    ("rs_DivideCurve", "rs.DivideCurve: divide curve into segments."),
    ("rs_EvaluateCurve", "rs.EvaluateCurve: evaluate point at parameter."),
    ("rs_OffsetCurve", "rs.OffsetCurve: offset curve by distance."),
    ("rs_JoinCurves", "rs.JoinCurves: join curves into polycurves."),
    ("rs_ExplodeCurves", "rs.ExplodeCurves: explode polycurves into segments."),
    ("rs_SplitCurve", "rs.SplitCurve: split curve at parameters."),
    ("rs_RebuildCurve", "rs.RebuildCurve: rebuild with degree and point count."),
    ("rs_ReverseCurve", "rs.ReverseCurve: reverse curve direction."),
    ("rs_CloseCurve", "rs.CloseCurve: close an open curve."),
    # Surface creation
    ("rs_AddSphere", "rs.AddSphere: add sphere."),
    ("rs_AddCylinder", "rs.AddCylinder: add cylinder."),
    ("rs_AddCone", "rs.AddCone: add cone."),
    ("rs_AddBox", "rs.AddBox: add box from 8 corners."),
    ("rs_AddTorus", "rs.AddTorus: add torus."),
    ("rs_AddPipe", "rs.AddPipe: pipe surfaces around a curve."),
    ("rs_AddPlanarSrf", "rs.AddPlanarSrf: planar surface from closed curves."),
    ("rs_AddLoftSrf", "rs.AddLoftSrf: loft surface through curves."),
    ("rs_AddSweep1", "rs.AddSweep1: sweep along one rail."),
    ("rs_AddSweep2", "rs.AddSweep2: sweep along two rails."),
    ("rs_AddRevSrf", "rs.AddRevSrf: surface of revolution."),
    ("rs_AddEdgeSrf", "rs.AddEdgeSrf: surface from 2-4 edge curves."),
    ("rs_AddNetworkSrf", "rs.AddNetworkSrf: surface from crossing curves."),
    ("rs_AddPatch", "rs.AddPatch: patch surface from curves/points."),
    # Surface operations
    ("rs_ExtrudeCurveStraight", "rs.ExtrudeCurveStraight: extrude between two points."),
    ("rs_CapPlanarHoles", "rs.CapPlanarHoles: cap planar holes in surface."),
    ("rs_FilletSurfaces", "rs.FilletSurfaces: fillet between two surfaces."),
    ("rs_OffsetSurface", "rs.OffsetSurface: offset surface by distance."),
    ("rs_JoinSurfaces", "rs.JoinSurfaces: join into polysurface."),
    ("rs_ExplodePolysurfaces", "rs.ExplodePolysurfaces: explode into surfaces."),
    ("rs_DuplicateEdgeCurves", "rs.DuplicateEdgeCurves: duplicate edge curves."),
    ("rs_DuplicateSurfaceBorder", "rs.DuplicateSurfaceBorder: duplicate border curves."),
    ("rs_ExtractIsoCurve", "rs.ExtractIsoCurve: extract U/V isocurve."),
    # Surface query
    ("rs_SurfaceArea", "rs.SurfaceArea: area of surface."),
    ("rs_SurfaceVolume", "rs.SurfaceVolume: volume of closed surface."),
    ("rs_SurfaceNormal", "rs.SurfaceNormal: normal at UV parameter."),
    ("rs_SurfaceDomain", "rs.SurfaceDomain: domain in U or V direction."),
    ("rs_EvaluateSurface", "rs.EvaluateSurface: point at UV parameter."),
    ("rs_BrepClosestPoint", "rs.BrepClosestPoint: closest point on brep."),
    ("rs_IsSurface", "rs.IsSurface: test if object is surface."),
    ("rs_IsPolysurface", "rs.IsPolysurface: test if object is polysurface."),
    ("rs_IsPolysurfaceClosed", "rs.IsPolysurfaceClosed: test if solid."),
    # Object operations
    ("rs_CopyObject", "rs.CopyObject: copy with optional translation."),
    ("rs_MoveObject", "rs.MoveObject: move by translation vector."),
    ("rs_RotateObject", "rs.RotateObject: rotate around point."),
    ("rs_ScaleObject", "rs.ScaleObject: scale from origin."),
    ("rs_MirrorObject", "rs.MirrorObject: mirror across line."),
    ("rs_ObjectLayer", "rs.ObjectLayer: get/set object layer."),
    ("rs_ObjectName", "rs.ObjectName: get/set object name."),
    ("rs_ObjectColor", "rs.ObjectColor: get/set object color."),
    ("rs_ObjectType", "rs.ObjectType: get object type integer."),
    # Geometry
    ("rs_AddPoint", "rs.AddPoint: add point at [x,y,z]."),
    ("rs_AddPoints", "rs.AddPoints: add multiple points."),
    ("rs_AddTextDot", "rs.AddTextDot: text dot at point."),
    ("rs_AddText", "rs.AddText: text object at point/plane."),
    ("rs_BoundingBox", "rs.BoundingBox: bounding box as 8 points."),
    ("rs_Area", "rs.Area: area of curve/surface/mesh."),
    ("rs_PointCoordinates", "rs.PointCoordinates: get point XYZ."),
    # Selection
    ("rs_AllObjects", "rs.AllObjects: all objects in document."),
    ("rs_ObjectsByLayer", "rs.ObjectsByLayer: objects on a layer."),
    ("rs_ObjectsByType", "rs.ObjectsByType: objects by geometry type."),
    ("rs_ObjectsByName", "rs.ObjectsByName: objects by name."),
    ("rs_SelectedObjects", "rs.SelectedObjects: currently selected GUIDs."),
    ("rs_UnselectAllObjects", "rs.UnselectAllObjects: deselect all."),
    ("rs_LastCreatedObjects", "rs.LastCreatedObjects: last created GUIDs."),
    # Layer
    ("rs_AddLayer", "rs.AddLayer: add new layer."),
    ("rs_CurrentLayer", "rs.CurrentLayer: get/set current layer."),
    ("rs_LayerVisible", "rs.LayerVisible: get/set layer visibility."),
    ("rs_LayerColor", "rs.LayerColor: get/set layer color."),
    ("rs_LayerNames", "rs.LayerNames: all layer names."),
    ("rs_RenameLayer", "rs.RenameLayer: rename a layer."),
    # View
    ("rs_ZoomExtents", "rs.ZoomExtents: zoom to fit all."),
    ("rs_ZoomSelected", "rs.ZoomSelected: zoom to selection."),
    ("rs_ViewCamera", "rs.ViewCamera: get/set camera position."),
    ("rs_CurrentView", "rs.CurrentView: get/set active view."),
    ("rs_Redraw", "rs.Redraw: force viewport redraw."),
    ("rs_EnableRedraw", "rs.EnableRedraw: enable/disable redraw."),
    # Document
    ("rs_UnitSystem", "rs.UnitSystem: get/set unit system."),
    ("rs_DocumentName", "rs.DocumentName: current document name."),
    # Mesh
    ("rs_AddMesh", "rs.AddMesh: add mesh from vertices/faces."),
    ("rs_MeshBooleanUnion", "rs.MeshBooleanUnion: union meshes."),
    ("rs_MeshBooleanDifference", "rs.MeshBooleanDifference: difference meshes."),
    ("rs_JoinMeshes", "rs.JoinMeshes: join meshes."),
    ("rs_MeshToNurb", "rs.MeshToNurb: convert mesh to NURBS."),
    ("rs_IsMesh", "rs.IsMesh: test if object is mesh."),
    # Utility
    ("rs_Distance", "rs.Distance: distance between two points."),
    ("rs_Angle", "rs.Angle: angle between two points."),
    ("rs_CullDuplicatePoints", "rs.CullDuplicatePoints: remove duplicate points."),
    # Transformation
    ("rs_XformScale", "rs.XformScale: scale transform matrix."),
    ("rs_XformTranslation", "rs.XformTranslation: translation transform matrix."),
    ("rs_TransformObject", "rs.TransformObject: apply transform matrix."),
    # Group
    ("rs_AddGroup", "rs.AddGroup: create new group."),
    ("rs_AddObjectsToGroup", "rs.AddObjectsToGroup: add objects to group."),
    ("rs_GroupNames", "rs.GroupNames: all group names."),
    # Material
    ("rs_AddMaterialToObject", "rs.AddMaterialToObject: add material to object."),
    ("rs_MaterialColor", "rs.MaterialColor: get/set material color."),
    # Block
    ("rs_InsertBlock", "rs.InsertBlock: insert block instance."),
    ("rs_ExplodeBlockInstance", "rs.ExplodeBlockInstance: explode block."),
    ("rs_BlockNames", "rs.BlockNames: all block names."),
    # Plane
    ("rs_PlaneFromNormal", "rs.PlaneFromNormal: plane from origin+normal."),
    ("rs_PlaneFromPoints", "rs.PlaneFromPoints: plane from 3 points."),
    ("rs_WorldXYPlane", "rs.WorldXYPlane: world XY plane."),
    # Userdata
    ("rs_SetUserText", "rs.SetUserText: set key-value on object."),
    ("rs_GetUserText", "rs.GetUserText: get key-value from object."),
    # Dimension
    ("rs_AddLinearDimension", "rs.AddLinearDimension: add linear dim."),
    ("rs_AddLeader", "rs.AddLeader: add leader annotation."),

    # --- Category catch-all tools (one per RhinoScriptSyntax category) ---
    ("rhinoscript_application", "Catch-all: any rs.* application function."),
    ("rhinoscript_block", "Catch-all: any rs.* block function."),
    ("rhinoscript_curve", "Catch-all: remaining rs.* curve functions not individually exposed."),
    ("rhinoscript_dimension", "Catch-all: remaining rs.* dimension functions."),
    ("rhinoscript_document", "Catch-all: remaining rs.* document functions."),
    ("rhinoscript_geometry", "Catch-all: remaining rs.* geometry functions."),
    ("rhinoscript_grips", "Catch-all: any rs.* grips function."),
    ("rhinoscript_group", "Catch-all: remaining rs.* group functions."),
    ("rhinoscript_hatch", "Catch-all: any rs.* hatch function."),
    ("rhinoscript_layer", "Catch-all: remaining rs.* layer functions."),
    ("rhinoscript_light", "Catch-all: any rs.* light function."),
    ("rhinoscript_line", "Catch-all: any rs.* line function."),
    ("rhinoscript_linetype", "Catch-all: any rs.* linetype function."),
    ("rhinoscript_material", "Catch-all: remaining rs.* material functions."),
    ("rhinoscript_mesh", "Catch-all: remaining rs.* mesh functions."),
    ("rhinoscript_object", "Catch-all: remaining rs.* object functions."),
    ("rhinoscript_plane", "Catch-all: remaining rs.* plane functions."),
    ("rhinoscript_pointvector", "Catch-all: any rs.* point/vector function."),
    ("rhinoscript_selection", "Catch-all: remaining rs.* selection functions."),
    ("rhinoscript_surface", "Catch-all: remaining rs.* surface functions."),
    ("rhinoscript_toolbar", "Catch-all: any rs.* toolbar function."),
    ("rhinoscript_transformation", "Catch-all: remaining rs.* transformation functions."),
    ("rhinoscript_userdata", "Catch-all: remaining rs.* userdata functions."),
    ("rhinoscript_userinterface", "Catch-all: any rs.* userinterface function."),
    ("rhinoscript_utility", "Catch-all: remaining rs.* utility functions."),
    ("rhinoscript_view", "Catch-all: remaining rs.* view functions."),

    # Discovery (full Rhino 7 API)
    ("list_rhino_commands", "Full roster of MCP commands; includes rs_function when mapped to Rhino 7."),
    ("list_rhinoscript_functions", "Full Rhino 7 RhinoScriptSyntax (rs.*) API: all function names by category."),
    ("look_up_RhinoScriptSyntax", "Look up detailed docs for any rs.* function by name."),
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
