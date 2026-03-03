"""Tools for interacting with Rhino through socket connection."""
from mcp.server.fastmcp import FastMCP, Context, Image
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Optional
import json
import socket
import time
import base64
import io
from PIL import Image as PILImage
import requests
import re
from rhino_mcp.resources.rhino_script_categories import get_function_category, get_all_functions, get_categories
from rhino_mcp.resources.rhino_command_roster import get_full_roster
import textwrap

# Configure logging
logger = logging.getLogger("RhinoTools")

class RhinoConnection:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.socket = None
        self.timeout = 120.0  # 2 minute timeout for complex operations
        self.buffer_size = 14485760  # 10MB buffer size for handling large images
    
    def connect(self):
        """Connect to the Rhino script's socket server"""
        if self.socket is None:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                self.socket.connect((self.host, self.port))
                logger.info("Connected to Rhino script")
            except Exception as e:
                logger.error("Failed to connect to Rhino script: {0}".format(str(e)))
                self.disconnect()
                raise
    
    def disconnect(self):
        """Disconnect from the Rhino script"""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
    
    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to the Rhino script and wait for response"""
        if self.socket is None:
            self.connect()
        
        try:
            # Prepare command
            command = {
                "type": command_type,
                "params": params or {}
            }
            
            # Send command (newline-delimited JSON framing)
            command_json = json.dumps(command) + "\n"
            logger.info("Sending command: {0}".format(command_json))
            self.socket.sendall(command_json.encode('utf-8'))
            
            # Receive response with timeout and larger buffer
            buffer = b''
            start_time = time.time()
            
            while True:
                try:
                    # Check timeout
                    if time.time() - start_time > self.timeout:
                        raise Exception("Response timeout after {0} seconds".format(self.timeout))
                    
                    # Receive data
                    data = self.socket.recv(self.buffer_size)
                    if not data:
                        break
                        
                    buffer += data
                    logger.debug("Received {0} bytes of data".format(len(data)))

                    # Parse one line (one JSON object) at a time
                    if b"\n" not in buffer:
                        continue
                    line, _, rest = buffer.partition(b"\n")
                    buffer = rest
                    if not line.strip():
                        continue
                    response = json.loads(line.decode('utf-8'))
                    logger.info("Received complete response: {0}".format(response))

                    # Check for error response
                    if response.get("status") == "error":
                        raise Exception(response.get("message", "Unknown error from Rhino"))

                    return response
                            
                except socket.timeout:
                    raise Exception("Socket timeout while receiving response")
                    
            raise Exception("Connection closed by Rhino script")
            
        except Exception as e:
            logger.error("Error communicating with Rhino script: {0}".format(str(e)))
            self.disconnect()  # Disconnect on error to force reconnection
            raise

# Global connection instance
_rhino_connection = None

def get_rhino_connection() -> RhinoConnection:
    """Get or create the Rhino connection"""
    global _rhino_connection
    if _rhino_connection is None:
        _rhino_connection = RhinoConnection()
    return _rhino_connection

class RhinoTools:
    """Collection of tools for interacting with Rhino."""
    
    def __init__(self, app):
        self.app = app
        self._register_tools()
    
    def _register_tools(self):
        """Register all Rhino tools with the MCP server."""
        self.app.tool()(self.get_rhino_scene_info)
        self.app.tool()(self.get_rhino_layers)
        self.app.tool()(self.get_rhino_objects_with_metadata)
        self.app.tool()(self.capture_rhino_viewport)
        self.app.tool()(self.execute_rhino_code)
        self.app.tool()(self.get_rhino_selected_objects)
        self.app.tool()(self.look_up_RhinoScriptSyntax)

        # RhinoMCP (plugin) contract-compatible tools
        self.app.tool()(self.get_document_summary)
        self.app.tool()(self.get_objects)
        self.app.tool()(self.get_object_info)
        self.app.tool()(self.get_selected_objects_info)
        self.app.tool()(self.create_layer)
        self.app.tool()(self.delete_layer)
        self.app.tool()(self.get_or_set_current_layer)
        self.app.tool()(self.create_object)
        self.app.tool()(self.delete_object)
        self.app.tool()(self.modify_object)
        self.app.tool()(self.select_objects)
        self.app.tool()(self.add_rhino_object_metadata)
        self.app.tool()(self.execute_rhinoscript_python_code)

        # Geometry tools (subset)
        self.app.tool()(self.boolean_union)
        self.app.tool()(self.boolean_difference)
        self.app.tool()(self.boolean_intersection)
        self.app.tool()(self.loft)
        self.app.tool()(self.extrude_curve)
        self.app.tool()(self.sweep1)
        self.app.tool()(self.offset_curve)
        self.app.tool()(self.pipe)
        self.app.tool()(self.trim_curve)
        self.app.tool()(self.join_curves)
        self.app.tool()(self.list_rhino_commands)
        self.app.tool()(self.list_rhinoscript_functions)

        # Jewelry helper tools (LLM-oriented)
        self.app.tool()(self.ring_blank)
        self.app.tool()(self.head_blank)
        self.app.tool()(self.edge_selector_presets)
        self.app.tool()(self.safe_boolean_union)
        self.app.tool()(self.safe_boolean_difference)
        self.app.tool()(self.loft_sections)

        # Grasshopper tools (same Rhino connection)
        self.app.tool()(self.grasshopper_add_components)
        self.app.tool()(self.grasshopper_get_definition_info)
        self.app.tool()(self.grasshopper_run_solver)
        self.app.tool()(self.grasshopper_clear_canvas)
        self.app.tool()(self.grasshopper_list_available_components)

    # ------------------------------
    # Contract-compatible tools
    # ------------------------------

    def get_document_summary(self, ctx: Context) -> str:
        """Get a compact summary of the current document (units, layers, object counts)."""
        try:
            result = get_rhino_connection().send_command("get_document_summary")
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error getting document summary: {0}".format(str(e))

    def get_objects(self, ctx: Context, filters: Optional[Dict[str, Any]] = None, limit: int = 500) -> str:
        """List objects in the document with optional filters (layer/name/type/selected_only)."""
        try:
            result = get_rhino_connection().send_command("get_objects", {
                "filters": filters or {},
                "limit": int(limit)
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error getting objects: {0}".format(str(e))

    def get_object_info(self, ctx: Context, object_id: str) -> str:
        """Get info about a single object by GUID string."""
        try:
            result = get_rhino_connection().send_command("get_object_info", {"object_id": object_id})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error getting object info: {0}".format(str(e))

    def get_selected_objects_info(self, ctx: Context) -> str:
        """Get info for currently selected objects."""
        try:
            result = get_rhino_connection().send_command("get_selected_objects_info")
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error getting selected objects info: {0}".format(str(e))

    def create_layer(self, ctx: Context, layer_name: str, parent: Optional[str] = None, color: Optional[List[int]] = None) -> str:
        """Create a layer (optionally nested under parent)."""
        try:
            result = get_rhino_connection().send_command("create_layer", {
                "layer_name": layer_name,
                "parent": parent,
                "color": color
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error creating layer: {0}".format(str(e))

    def delete_layer(self, ctx: Context, layer_name: str, purge: bool = False) -> str:
        """Delete a layer by name."""
        try:
            result = get_rhino_connection().send_command("delete_layer", {
                "layer_name": layer_name,
                "purge": bool(purge)
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error deleting layer: {0}".format(str(e))

    def get_or_set_current_layer(self, ctx: Context, layer_name: Optional[str] = None) -> str:
        """Get current layer, or set it if layer_name provided."""
        try:
            result = get_rhino_connection().send_command("get_or_set_current_layer", {"layer_name": layer_name})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error getting/setting current layer: {0}".format(str(e))

    def create_object(self, ctx: Context, object_type: str, params: Optional[Dict[str, Any]] = None, attributes: Optional[Dict[str, Any]] = None) -> str:
        """Create an object. object_type examples: point, line, polyline, circle, rectangle, box, sphere, cylinder."""
        try:
            result = get_rhino_connection().send_command("create_object", {
                "object_type": object_type,
                "params": params or {},
                "attributes": attributes or {}
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error creating object: {0}".format(str(e))

    def delete_object(self, ctx: Context, object_id: str) -> str:
        """Delete an object by GUID string."""
        try:
            result = get_rhino_connection().send_command("delete_object", {"object_id": object_id})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error deleting object: {0}".format(str(e))

    def modify_object(self, ctx: Context, object_id: str, operations: Dict[str, Any]) -> str:
        """Modify an object (transform + attributes)."""
        try:
            result = get_rhino_connection().send_command("modify_object", {
                "object_id": object_id,
                "operations": operations
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error modifying object: {0}".format(str(e))

    def select_objects(self, ctx: Context, filters: Dict[str, Any], mode: str = "replace") -> str:
        """Select objects by filters (layer/name/type/ids). mode: replace/add/subtract."""
        try:
            result = get_rhino_connection().send_command("select_objects", {
                "filters": filters,
                "mode": mode
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error selecting objects: {0}".format(str(e))

    def add_rhino_object_metadata(self, ctx: Context, object_id: str, name: Optional[str] = None, description: Optional[str] = None) -> str:
        """Add name and description metadata to an object so it can be filtered with get_rhino_objects_with_metadata. Call after creating objects."""
        try:
            result = get_rhino_connection().send_command("add_rhino_object_metadata", {
                "object_id": object_id,
                "name": name,
                "description": description
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error adding object metadata: {0}".format(str(e))

    def execute_rhinoscript_python_code(self, ctx: Context, code: str) -> str:
        """Execute IronPython code inside Rhino (same as execute_rhino_code, but contract name)."""
        try:
            result = get_rhino_connection().send_command("execute_rhinoscript_python_code", {"code": code})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error executing script: {0}".format(str(e))

    # ------------------------------
    # Geometry tools (subset)
    # ------------------------------

    def boolean_union(self, ctx: Context, object_ids: List[str]) -> str:
        try:
            result = get_rhino_connection().send_command("boolean_union", {"object_ids": object_ids})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error boolean union: {0}".format(str(e))

    def boolean_difference(self, ctx: Context, base_id: str, cutter_ids: List[str]) -> str:
        try:
            result = get_rhino_connection().send_command("boolean_difference", {"base_id": base_id, "cutter_ids": cutter_ids})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error boolean difference: {0}".format(str(e))

    def boolean_intersection(self, ctx: Context, object_ids: List[str]) -> str:
        try:
            result = get_rhino_connection().send_command("boolean_intersection", {"object_ids": object_ids})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error boolean intersection: {0}".format(str(e))

    def loft(self, ctx: Context, curve_ids: List[str], closed: bool = False) -> str:
        try:
            result = get_rhino_connection().send_command("loft", {"curve_ids": curve_ids, "closed": bool(closed)})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error loft: {0}".format(str(e))

    def extrude_curve(self, ctx: Context, curve_id: str, direction: List[float], cap: bool = True) -> str:
        try:
            result = get_rhino_connection().send_command("extrude_curve", {"curve_id": curve_id, "direction": direction, "cap": bool(cap)})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error extrude curve: {0}".format(str(e))

    def sweep1(self, ctx: Context, rail_id: str, shape_ids: List[str], closed: bool = False) -> str:
        try:
            result = get_rhino_connection().send_command("sweep1", {"rail_id": rail_id, "shape_ids": shape_ids, "closed": bool(closed)})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error sweep1: {0}".format(str(e))

    def offset_curve(self, ctx: Context, curve_id: str, distance: float, plane: str = "WorldXY") -> str:
        try:
            result = get_rhino_connection().send_command("offset_curve", {"curve_id": curve_id, "distance": float(distance), "plane": plane})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error offset curve: {0}".format(str(e))

    def pipe(self, ctx: Context, curve_id: str, radius: float, cap: str = "round") -> str:
        try:
            result = get_rhino_connection().send_command("pipe", {"curve_id": curve_id, "radius": float(radius), "cap": cap})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error pipe: {0}".format(str(e))

    def curve_domain(self, ctx: Context, curve_id: str) -> str:
        """Return the curve parameter domain [t0, t1] for a Rhino curve."""
        try:
            result = get_rhino_connection().send_command("curve_domain", {"curve_id": curve_id})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error getting curve domain: {0}".format(str(e))

    def trim_curve_by_fraction(self, ctx: Context, curve_id: str, start_fraction: float, end_fraction: float, delete_input: bool = True) -> str:
        """Trim a curve using fractional parameters (0..1) mapped over its domain."""
        try:
            result = get_rhino_connection().send_command("trim_curve_by_fraction", {
                "curve_id": curve_id, 
                "start_fraction": float(start_fraction), 
                "end_fraction": float(end_fraction), 
                "delete_input": bool(delete_input)
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error trimming curve by fraction: {0}".format(str(e))

    def trim_curve(self, ctx: Context, curve_id: str, interval_min: float, interval_max: float, delete_input: bool = True) -> str:
        """Trim a curve to the parameter interval [interval_min, interval_max] (the portion to keep).
        Use curve_domain or CurveDomain in code to get the curve's parameter range."""
        try:
            result = get_rhino_connection().send_command("trim_curve", {
                "curve_id": curve_id,
                "interval_min": float(interval_min),
                "interval_max": float(interval_max),
                "delete_input": bool(delete_input),
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error trim curve: {0}".format(str(e))

    def validate_command_roster(self, ctx: Optional[Context] = None) -> str:
        """Validate that the command roster matches the currently exposed MCP tool methods.
        Returns missing/extra command names relative to MCP_TO_RS_MAP keys."""
        try:
            from rhino_mcp.resources.rhino_command_roster import MCP_TO_RS_MAP
            roster_cmds = set(MCP_TO_RS_MAP.keys())

            # Exposed methods on this class that forward to Rhino (heuristic)
            method_names = [n for n in dir(self) if callable(getattr(self, n)) and not n.startswith("_")]
            # Filter to likely command methods (exclude obvious non-tools)
            blacklist = set(["send_command", "connect", "disconnect", "is_connected", "ensure_connected"])
            tool_methods = set([n for n in method_names if n not in blacklist])

            missing = sorted(list(roster_cmds - tool_methods))
            extra = sorted(list(tool_methods - roster_cmds))

            return json.dumps({
                "status": "ok",
                "roster_count": len(roster_cmds),
                "tool_method_count": len(tool_methods),
                "missing_in_tools": missing,
                "extra_in_tools": extra,
                "note": "This is a heuristic check. Tools that don't map 1:1 to commands may appear as 'extra'."
            }, indent=2)
        except Exception as e:
            return "Error validating command roster: {0}".format(str(e))


    def list_rhinoscript_functions(self, ctx: Optional[Context] = None, category: Optional[str] = None, include_functions: bool = False, offset: int = 0, limit: int = 200) -> str:
        """Return the full Rhino 7 RhinoScriptSyntax (rs.*) API: every function name and its category.
        This matches the full set of tools available in Rhino 7. Use look_up_RhinoScriptSyntax(name) for
        docs and execute_rhino_code() to call rs.<name>(...). Optionally filter by category (e.g. curve,
        surface, mesh, object, layer, curve, document, view)."""
try:
    categories = get_categories()
    # Default behavior: return categories only (small payload) unless include_functions
    # or a category filter is provided.
    if not include_functions and not category:
        return json.dumps({
            "categories": categories,
            "count_categories": len(categories),
            "usage": "Pass category='<name>' or include_functions=true (optionally with offset/limit) to list functions."
        }, indent=2)

    funcs = get_all_functions(category=category)
    total = len(funcs)

    # paging for smaller models
    if offset < 0:
        offset = 0
    if limit is None or limit <= 0:
        limit = 200
    page = funcs[offset: offset + limit]

    return json.dumps({
        "category": category,
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "count": total,
        "categories": categories,
        "functions": page,
        "usage": "Use look_up_RhinoScriptSyntax(function_name) for docs; execute_rhino_code() to call rs.<name>(...)."
    }, indent=2)
except Exception as e:
            return "Error listing RhinoScript functions: {0}".format(str(e))

    # ------------------------------
    # Grasshopper tools (same Rhino socket connection)
    # ------------------------------

    def grasshopper_add_components(self, ctx: Context, components: List[Dict[str, Any]]) -> str:
        """Add components to the active Grasshopper definition. components: list of {name, position [x,y], [optional] params}."""
        try:
            result = get_rhino_connection().send_command("grasshopper_add_components", {"components": components})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error adding Grasshopper components: {0}".format(str(e))

    def grasshopper_get_definition_info(self, ctx: Optional[Context] = None) -> str:
        """Get info about the current Grasshopper definition (editor loaded, component count, etc.)."""
        try:
            result = get_rhino_connection().send_command("grasshopper_get_definition_info")
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error getting Grasshopper definition info: {0}".format(str(e))

    def grasshopper_run_solver(self, ctx: Context, force_update: bool = True) -> str:
        """Run the Grasshopper solver to update the definition."""
        try:
            result = get_rhino_connection().send_command("grasshopper_run_solver", {"force_update": force_update})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error running Grasshopper solver: {0}".format(str(e))

    def grasshopper_clear_canvas(self, ctx: Optional[Context] = None) -> str:
        """Clear all components from the Grasshopper canvas."""
        try:
            result = get_rhino_connection().send_command("grasshopper_clear_canvas")
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error clearing Grasshopper canvas: {0}".format(str(e))

    def grasshopper_list_available_components(self, ctx: Optional[Context] = None) -> str:
        """List available Grasshopper component types (for add_components)."""
        try:
            result = get_rhino_connection().send_command("grasshopper_list_available_components")
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error listing Grasshopper components: {0}".format(str(e))

    # ------------------------------
    # Jewelry helper tools (LLM-oriented)
    # ------------------------------

    def ring_blank(self, ctx: Context, inner_diameter_mm: float, band_width_mm: float, band_thickness_mm: float,
               profile: str = "flat", center: Optional[List[float]] = None, comfort_radius_mm: Optional[float] = None) -> str:
        """Create a robust ring blank solid (cylinder outer minus inner).
        Returns ring_id and computed radii. Intended as a stable starting primitive for jewelry workflows.
        """
        try:
            params = {
                "inner_diameter_mm": float(inner_diameter_mm),
                "band_width_mm": float(band_width_mm),
                "band_thickness_mm": float(band_thickness_mm),
                "profile": profile,
                "center": center or [0.0, 0.0, 0.0],
            }
            if comfort_radius_mm is not None:
                params["comfort_radius_mm"] = float(comfort_radius_mm)
            result = get_rhino_connection().send_command("ring_blank", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error ring_blank: {0}".format(str(e))

    def head_blank(self, ctx: Context, shape: str, length_mm: float, width_mm: float, height_mm: float,
              center: Optional[List[float]] = None, corner_radius_mm: Optional[float] = None) -> str:
        """Create a head blank solid by extruding a planar curve +Z."""
        try:
            params = {
                "shape": shape,
                "length_mm": float(length_mm),
                "width_mm": float(width_mm),
                "height_mm": float(height_mm),
                "center": center or [0.0, 0.0, 0.0],
            }
            if corner_radius_mm is not None:
                params["corner_radius_mm"] = float(corner_radius_mm)
            result = get_rhino_connection().send_command("head_blank", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error head_blank: {0}".format(str(e))

    def section_profile(self, ctx: Context, center: List[float], width_mm: float, height_mm: float,
                    plane: str = "XZ", shape: str = "rounded_rect", corner_radius_mm: Optional[float] = None) -> str:
        """Create a standardized section profile curve for lofting shoulders/bridges.
        Returns curve_id. This reduces LLM improvisation around curve construction.
        """
        try:
            params = {
                "center": center,
                "width_mm": float(width_mm),
                "height_mm": float(height_mm),
                "plane": plane,
                "shape": shape,
            }
            if corner_radius_mm is not None:
                params["corner_radius_mm"] = float(corner_radius_mm)
            result = get_rhino_connection().send_command("section_profile", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error section_profile: {0}".format(str(e))

    def place_head_on_band(self, ctx: Context, ring_id: str, head_id: str, side: str = "+Y",
                       offset_mm: float = 0.0, embed_mm: float = 0.2, align_x: bool = True, align_z: str = "top") -> str:
        """Deterministically place a head blank relative to a ring blank using bbox heuristics.
        Returns the applied move vector and computed placement info.
        """
        try:
            params = {
                "ring_id": ring_id,
                "head_id": head_id,
                "side": side,
                "offset_mm": float(offset_mm),
                "embed_mm": float(embed_mm),
                "align_x": bool(align_x),
                "align_z": align_z,
            }
            result = get_rhino_connection().send_command("place_head_on_band", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error place_head_on_band: {0}".format(str(e))

    def edge_selector_presets(self, ctx: Context, object_id: str, preset: str) -> str:
        """Heuristic edge selection helper to avoid LLM guessing edge indices."""
        try:
            result = get_rhino_connection().send_command("edge_selector_presets", {"object_id": object_id, "preset": preset})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error edge_selector_presets: {0}".format(str(e))

    def safe_boolean_union(self, ctx: Context, object_ids: List[str]) -> str:
        """Best-effort boolean union with pairwise fallback."""
        try:
            result = get_rhino_connection().send_command("safe_boolean_union", {"object_ids": object_ids})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error safe_boolean_union: {0}".format(str(e))

    def safe_boolean_difference(self, ctx: Context, base_id: str, cutter_ids: List[str]) -> str:
        """Best-effort boolean difference with sequential fallback."""
        try:
            result = get_rhino_connection().send_command("safe_boolean_difference", {"base_id": base_id, "cutter_ids": cutter_ids})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error safe_boolean_difference: {0}".format(str(e))

    def loft_sections(self, ctx: Context, curve_ids: List[str], cap: bool = False) -> str:
        """Loft between section curves; optional cap."""
        try:
            result = get_rhino_connection().send_command("loft_sections", {"curve_ids": curve_ids, "cap": bool(cap)})
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error loft_sections: {0}".format(str(e))

    def execute_command(self, command: Dict[str, Any]) -> Any:
        """Execute a raw command on Rhino (type + params). Used by HTTP/WebSocket."""
        cmd_type = command.get("type") if isinstance(command, dict) else None
        params = command.get("params", {}) if isinstance(command, dict) else {}
        if not cmd_type:
            raise ValueError("command must be a dict with 'type'")
        return get_rhino_connection().send_command(cmd_type, params)

    def get_rhino_scene_info(self, ctx: Optional[Context] = None) -> str:
        """Get basic information about the current Rhino scene.
        
        This is a lightweight function that returns basic scene information:
        - the Unit of Measure of current file
        - List of all layers with basic information about the layer and 5 sample objects with their metadata 
        - No metadata or detailed properties
        - Use this for quick scene overview or when you only need basic object information
        
        Returns:
            JSON string containing basic scene information
        """
        try:
            connection = get_rhino_connection()
            result = connection.send_command("get_rhino_scene_info")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error("Error getting scene info from Rhino: {0}".format(str(e)))
            return "Error getting scene info: {0}".format(str(e))

    def get_rhino_layers(self, ctx: Context) -> str:
        """Get list of layers in Rhino"""
        try:
            connection = get_rhino_connection()
            result = connection.send_command("get_rhino_layers")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error("Error getting layers from Rhino: {0}".format(str(e)))
            return "Error getting layers: {0}".format(str(e))

    def get_rhino_objects_with_metadata(self, ctx: Context, filters: Optional[Dict[str, Any]] = None, metadata_fields: Optional[List[str]] = None) -> str:
        """Get detailed information about objects in the scene with their metadata.
        
        This is a CORE FUNCTION for scene context awareness. It provides:
        1. Full metadata for each object we created via this mcp connection including:
           - short_id (DDHHMMSS format), can be dispalyed in the viewport when using capture_rhino_viewport, can help visually identify the a object and find it with this function
           - created_at timestamp
           - layer  - layer path
           - type - geometry type 
           - bbox - the bounding box as lsit of points
           - name - the name you assigned 
           - description - description you assigned 
        
        2. Advanced filtering capabilities:
           - layer: Filter by layer name (supports wildcards, e.g., "Layer*")
           - name: Filter by object name (supports wildcards, e.g., "Cube*")
           - short_id: Filter by exact short ID match
        
        3. Field selection:
           - Can specify which metadata fields to return
           - Useful for reducing response size when only certain fields are needed
        
        Args:
            filters: Optional dictionary of filters to apply
            metadata_fields: Optional list of specific metadata fields to return
        
        Returns:
            JSON string containing filtered objects with their metadata
        """
        try:
            connection = get_rhino_connection()
            result = connection.send_command("get_rhino_objects_with_metadata", {
                "filters": filters or {},
                "metadata_fields": metadata_fields
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error("Error getting objects with metadata: {0}".format(str(e)))
            return "Error getting objects with metadata: {0}".format(str(e))

    def capture_rhino_viewport(self, ctx: Context, layer: Optional[str] = None, show_annotations: bool = True, max_size: int = 800) -> Image:
        """Capture the current viewport as an image.
        
        Args:
            layer: Optional layer name to filter annotations
            show_annotations: Whether to show object annotations, this will display the short_id of the object in the viewport you can use the short_id to select specific objects with the get_rhino_objects_with_metadata function
        
        Returns:
            An MCP Image object containing the viewport capture
        """
        try:
            connection = get_rhino_connection()
            result = connection.send_command("capture_rhino_viewport", {
                "layer": layer,
                "show_annotations": show_annotations,
                "max_size": max_size
            })
            
            if result.get("type") == "image":
                # Get base64 data from Rhino
                base64_data = result["source"]["data"]
                
                # Convert base64 to bytes
                image_bytes = base64.b64decode(base64_data)
                
                # Create PIL Image from bytes
                img = PILImage.open(io.BytesIO(image_bytes))
                
                # Convert to PNG format for better quality and consistency
                png_buffer = io.BytesIO()
                img.save(png_buffer, format="PNG")
                png_bytes = png_buffer.getvalue()
                
                # Return as MCP Image object
                return Image(data=png_bytes, format="png")
                
            else:
                raise Exception(result.get("text", "Failed to capture viewport"))
                
        except Exception as e:
            logger.error("Error capturing viewport: {0}".format(str(e)))
            raise

    def execute_rhino_code(self, ctx: Context, code: str) -> str:
        """Execute arbitrary Python code in Rhino.
        
        IMPORTANT NOTES FOR CODE EXECUTION:
        0. DONT FORGET NO f-strings! No f-strings, No f-strings!
        1. This is Rhino 7 with IronPython 2.7 - no f-strings or modern Python features
        3. When creating objects, ALWAYS call add_rhino_object_metadata(name, description) after creation
        4. For user interaction, you can use RhinoCommon syntax (selected_objects = rs.GetObjects("Please select some objects") etc.) prompted the suer what to do 
           but prefer automated solutions unless user interaction is specifically requested
        5. Always show the user the code you are executing   
        
        The add_rhino_object_metadata() function is provided in the code context and must be called
        after creating any object. It adds standardized metadata including:
        - name (provided by you)
        - description (provided by you)
        The metadata helps you to identify and select objects later in the scene and stay organised.

        Common Syntax Errors to Avoid:
        2. No walrus operator (:=)
        3. No type hints
        4. No modern Python features (match/case, etc.)
        5. No list/dict comprehensions with multiple for clauses
        6. No assignment expressions in if/while conditions

        Example of proper object creation:
        <<<python
        # Create geometry
        cube_id = rs.AddBox(corners)
        # Add metadata - ALWAYS do this after creating an object
        add_rhino_object_metadata(cube_id, "My Cube", "A test cube created via MCP")

        >>>
        """
        try:
            code_template = """
import rhinoscriptsyntax as rs
import scriptcontext as sc
import json
import time
from datetime import datetime

def add_rhino_object_metadata(obj_id, name=None, description=None):
    # Add standardized metadata to an object
    try:
        # Generate short ID
        short_id = datetime.now().strftime("%d%H%M%S")
        
        # Get bounding box
        bbox = rs.BoundingBox(obj_id)
        bbox_data = [[p.X, p.Y, p.Z] for p in bbox] if bbox else []
        
        # Get object type
        obj = sc.doc.Objects.Find(obj_id)
        obj_type = obj.Geometry.GetType().Name if obj else "Unknown"
        
        # Standard metadata
        metadata = {
            "short_id": short_id,
            "created_at": time.time(),
            "layer": rs.ObjectLayer(obj_id),
            "type": obj_type,
            "bbox": bbox_data
        }
        
        # User-provided metadata
        if name:
            rs.ObjectName(obj_id, name)
            metadata["name"] = name
        else:
            auto_name = "{0}_{1}".format(obj_type, short_id)
            rs.ObjectName(obj_id, auto_name)
            metadata["name"] = auto_name
            
        if description:
            metadata["description"] = description
            
        # Store metadata as user text
        user_text_data = metadata.copy()
        user_text_data["bbox"] = json.dumps(bbox_data)
        
        for key, value in user_text_data.items():
            rs.SetUserText(obj_id, key, str(value))
            
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
            """ 
            combined_code = code_template + "\n# --- User Code Start ---\n" + textwrap.dedent(code).lstrip() + "\n"
            logger.info("Sending code execution request to Rhino")
            connection = get_rhino_connection()
            result = connection.send_command("execute_code", {"code": combined_code})
            
            logger.info("Received response from Rhino: {0}".format(result))
            
            # Handle the response including printed output
            if result.get("status") == "error":
                error_msg = "Error: {0}".format(result.get("message", "Unknown error"))
                printed_output = result.get("printed_output", [])
                if printed_output:
                    error_msg += "\n\nPrinted output before error:\n" + "\n".join(printed_output)
                logger.error("Code execution error: {0}".format(error_msg))
                return error_msg
            else:
                response = result.get("result", "Code executed successfully")
                printed_output = result.get("printed_output", [])
                if printed_output:
                    response += "\n\nPrinted output:\n" + "\n".join(printed_output)
                logger.info("Code execution successful: {0}".format(response))
                return response
                
        except Exception as e:
            error_msg = "Error executing code: {0}".format(str(e))
            logger.error(error_msg)
            return error_msg

    def get_rhino_selected_objects(self, ctx: Context, include_lights: bool = False, include_grips: bool = False) -> str:
        """Get the identifiers of all objects that are currently selected in Rhino.
        
        This tool provides access to objects that have been manually selected in the Rhino viewport.
        It returns a list of object identifiers (GUIDs) that can be used with other Rhino functions.
        
        Args:
            include_lights: Whether to include light objects in the selection
            include_grips: Whether to include grip objects in the selection
        
        Returns:
            JSON string containing the selected object identifiers and metadata
        """
        try:
            connection = get_rhino_connection()
            result = connection.send_command("get_rhino_selected_objects", {
                "include_lights": include_lights,
                "include_grips": include_grips
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error("Error getting selected objects from Rhino: {0}".format(str(e)))
            return "Error getting selected objects: {0}".format(str(e))

    def look_up_RhinoScriptSyntax(self, ctx: Context, function_name: str) -> str:
        """Look up the documentation for a RhinoScriptSyntax function.
        
        This tool fetches the detailed API documentation for a specified RhinoScriptSyntax function
        directly from the GitHub source code repository.
        
        Args:
            function_name: The name of the RhinoScriptSyntax function to look up
            
        Returns:
            str: The documentation for the function including signature, parameters, returns, and examples
        """
        try:
            # Get the category for the function
            category = get_function_category(function_name)
            if not category:
                return f"Function '{function_name}' not found in RhinoScriptSyntax categories"
            
            # Construct the URL to the GitHub repository source code 
            # the raw.githubusercontent.com/... gives raw source code
            github_url = f"https://raw.githubusercontent.com/mcneel/rhinoscriptsyntax/rhino-8.x/Scripts/rhinoscript/{category}.py"
            logger.info(f"Looking up documentation at URL: {github_url}")
            
            # Fetch the Python source file
            response = requests.get(github_url)
            if response.status_code != 200:
                return f"Failed to fetch source code for category '{category}' (HTTP status: {response.status_code})"
            
            # Parse the Python file to find the function definition and docstring
            source_code = response.text
            
            # Look for the function definition
            function_pattern = re.compile(f"def {function_name}\\s*\\(.*?\\):", re.DOTALL)
            function_match = function_pattern.search(source_code)
            if not function_match:
                return f"Function '{function_name}' not found in the source code for category '{category}'"
            
            # Find the start of the function
            function_start = function_match.start()
            
            # Extract the docstring
            docstring_start = source_code.find('"""', function_start)
            if docstring_start == -1:
                return f"No documentation found for function '{function_name}'"
            
            docstring_end = source_code.find('"""', docstring_start + 3)
            if docstring_end == -1:
                return f"Malformed documentation for function '{function_name}'"
            
            docstring = source_code[docstring_start + 3:docstring_end].strip()
            
            # Format the docstring into Markdown
            documentation = []
            
            # Add the function name as a header
            documentation.append(f"# {function_name}")
            documentation.append("")
            
            # Add the function signature
            function_def = function_match.group(0).strip()[4:-1]  # Remove 'def ' prefix and ':' suffix
            documentation.append("```python")
            documentation.append(function_def)
            documentation.append("```")
            documentation.append("")
            
            # Process the docstring into sections
            lines = docstring.split("\n")
            current_section = "Description"
            sections = {"Description": []}
            
            for line in lines:
                line = line.strip()
                # Remove leading spaces that might be part of the docstring formatting
                if line.startswith(" "):
                    line = line.lstrip()
                
                # Check if this is a section header
                if line.endswith(":") and not line.startswith(" "):
                    current_section = line[:-1]  # Remove the colon
                    if current_section not in sections:
                        sections[current_section] = []
                else:
                    sections[current_section].append(line)
            
            # Format each section
            for section, content in sections.items():
                if section == "Description" and content:
                    for line in content:
                        if line:
                            documentation.append(line)
                    documentation.append("")
                elif section == "Parameters" and content:
                    documentation.append(f"## {section}")
                    for line in content:
                        if line:
                            documentation.append(f"- {line}")
                    documentation.append("")
                elif section == "Returns" and content:
                    documentation.append(f"## {section}")
                    for line in content:
                        if line:
                            documentation.append(f"- {line}")
                    documentation.append("")
                elif section == "Example" and content:
                    documentation.append(f"## {section}")
                    # Find the start of code blocks
                    in_code_block = False
                    for line in content:
                        if not in_code_block and (line.strip().startswith("import") or line.strip().startswith("rs.")):
                            documentation.append("```python")
                            in_code_block = True
                        
                        if in_code_block and not line.strip() and "```" not in documentation[-1]:
                            documentation.append("```")
                            in_code_block = False
                        
                        documentation.append(line)
                    
                    if in_code_block:
                        documentation.append("```")
                    documentation.append("")
                elif section == "See Also" and content:
                    documentation.append(f"## {section}")
                    items = []
                    for line in content:
                        if line.strip():
                            items.append(line.strip())
                    
                    for item in items:
                        documentation.append(f"- {item}")
                    documentation.append("")
            
            # Add a link to the GitHub repository
            github_view_url = f"https://github.com/mcneel/rhinoscriptsyntax/blob/rhino-8.x/Scripts/rhinoscript/{category}.py"
            documentation.append(f"[View source code on GitHub]({github_view_url})")
            
            return "\n".join(documentation)
            
        except Exception as e:
            logger.error(f"Error looking up RhinoScriptSyntax documentation: {str(e)}")
            return f"Error fetching documentation: {str(e)}"