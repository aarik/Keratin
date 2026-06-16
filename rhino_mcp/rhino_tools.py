"""Tools for interacting with Rhino through socket connection."""
from mcp.server.fastmcp import FastMCP, Context, Image
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Optional
import json
import socket
import time
import threading
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
        self._recv_size = 65536  # recv chunk size per call
        self._lock = threading.Lock()  # Serialize connect/disconnect/send_command

    def connect(self):
        """Connect to the Rhino script's socket server"""
        with self._lock:
            if self.socket is None:
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.settimeout(self.timeout)
                    self.socket.connect((self.host, self.port))
                    logger.info("Connected to Rhino script")
                except Exception as e:
                    logger.error("Failed to connect to Rhino script: {0}".format(str(e)))
                    self._disconnect_unlocked()
                    raise

    def _disconnect_unlocked(self):
        """Disconnect without acquiring the lock (caller must hold it)."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

    def disconnect(self):
        """Disconnect from the Rhino script"""
        with self._lock:
            self._disconnect_unlocked()

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to the Rhino script and wait for response.
        Thread-safe: only one command can be in-flight at a time."""
        with self._lock:
            if self.socket is None:
                # Connect inside the lock so two callers don't race
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.settimeout(self.timeout)
                    self.socket.connect((self.host, self.port))
                    logger.info("Connected to Rhino script (auto-reconnect)")
                except Exception as e:
                    logger.error("Failed to connect to Rhino script: {0}".format(str(e)))
                    self._disconnect_unlocked()
                    raise

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

                # Receive response with timeout
                buffer = b''
                start_time = time.time()
                max_buffer = 15 * 1024 * 1024  # 15 MB safety cap

                while True:
                    try:
                        # Check timeout
                        if time.time() - start_time > self.timeout:
                            raise Exception("Response timeout after {0} seconds".format(self.timeout))

                        # Receive data in reasonable chunks
                        data = self.socket.recv(self._recv_size)
                        if not data:
                            break

                        buffer += data
                        if len(buffer) > max_buffer:
                            raise Exception("Response exceeded {0} byte safety limit".format(max_buffer))
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
                self._disconnect_unlocked()  # Disconnect on error to force reconnection
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

        # --- New individual RhinoScript tools (high-frequency functions) ---
        self._register_individual_rs_tools()

        # --- Category-level catch-all tools ---
        self._register_category_tools()

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

    def join_curves(self, ctx: Context, curve_ids: List[str], delete_input: bool = False, tolerance: Optional[float] = None) -> str:
        """Join two or more curves into one or more polycurves wherever endpoints are within tolerance.
        Returns the list of resulting curve IDs."""
        try:
            params = {"curve_ids": curve_ids, "delete_input": bool(delete_input)}
            if tolerance is not None:
                params["tolerance"] = float(tolerance)
            result = get_rhino_connection().send_command("join_curves", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return "Error joining curves: {0}".format(str(e))

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

    def list_rhino_commands(self, ctx: Optional[Context] = None) -> str:
        """Return every MCP tool name this server exposes, with its description and parameter list.
        Use this to discover what operations are available before choosing a tool."""
        try:
            from rhino_mcp.resources.rhino_command_roster import RHINO_COMMAND_ROSTER
            return json.dumps({
                "status": "ok",
                "count": len(RHINO_COMMAND_ROSTER),
                "commands": RHINO_COMMAND_ROSTER,
            }, indent=2)
        except Exception as e:
            return "Error listing rhino commands: {0}".format(str(e))

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

    # ------------------------------------------------------------------
    # Individual RhinoScript tools (popular rs.* functions with typed params)
    # ------------------------------------------------------------------

    # Which rs.* functions are exposed as individual tools (excluded from category catch-alls)
    INDIVIDUAL_RS_FUNCTIONS = {
        # Curve creation
        "AddLine", "AddPolyline", "AddCircle", "AddArc3Pt", "AddEllipse",
        "AddInterpCurve", "AddNurbsCurve", "AddRectangle", "AddSpiral",
        "AddBlendCurve", "AddFilletCurve",
        # Curve query
        "CurveLength", "CurveStartPoint", "CurveEndPoint", "CurveMidPoint",
        "CurveClosestPoint", "CurveDomain", "CurveDegree", "CurvePointCount",
        "CurvePoints", "CurveTangent", "CurveFrame", "CurveArea",
        "IsCurve", "IsCurveClosed", "IsCurvePlanar",
        # Curve operations
        "DivideCurve", "DivideCurveEquidistant", "EvaluateCurve",
        "OffsetCurve", "JoinCurves", "ExplodeCurves", "TrimCurve",
        "SplitCurve", "ExtendCurve", "ExtendCurveLength",
        "RebuildCurve", "ReverseCurve", "CloseCurve", "FitCurve",
        # Surface creation
        "AddSphere", "AddCylinder", "AddCone", "AddBox", "AddTorus",
        "AddPipe", "AddPlanarSrf", "AddLoftSrf", "AddSweep1", "AddSweep2",
        "AddRevSrf", "AddEdgeSrf", "AddNetworkSrf", "AddPatch",
        "AddNurbsSurface", "AddSrfPt", "AddPlaneSurface",
        # Surface operations
        "ExtrudeCurve", "ExtrudeCurveStraight", "ExtrudeSurface",
        "BooleanUnion", "BooleanDifference", "BooleanIntersection",
        "CapPlanarHoles", "FilletSurfaces", "OffsetSurface",
        "SplitBrep", "TrimBrep", "JoinSurfaces",
        "DuplicateEdgeCurves", "DuplicateSurfaceBorder",
        "ExplodePolysurfaces", "ExtractIsoCurve",
        # Surface query
        "SurfaceArea", "SurfaceVolume", "SurfaceNormal",
        "SurfaceDomain", "SurfaceClosestPoint", "EvaluateSurface",
        "IsSurface", "IsPolysurface", "IsPolysurfaceClosed", "IsBrep",
        "BrepClosestPoint",
        # Object operations
        "CopyObject", "CopyObjects", "DeleteObject", "DeleteObjects",
        "MoveObject", "MoveObjects", "RotateObject", "ScaleObject",
        "MirrorObject", "TransformObject",
        "HideObject", "ShowObject", "LockObject", "UnlockObject",
        # Object properties
        "ObjectLayer", "ObjectName", "ObjectColor", "ObjectType",
        "ObjectMaterialIndex", "ObjectGroups", "IsObject", "IsObjectSolid",
        "MatchObjectAttributes",
        # Layer
        "AddLayer", "DeleteLayer", "CurrentLayer", "LayerVisible",
        "LayerColor", "LayerNames", "LayerLocked", "RenameLayer",
        "PurgeLayer", "IsLayer", "LayerChildren", "ParentLayer",
        # Geometry
        "AddPoint", "AddPoints", "AddTextDot", "AddText",
        "BoundingBox", "Area", "PointCoordinates",
        # Selection
        "AllObjects", "ObjectsByLayer", "ObjectsByType", "ObjectsByName",
        "ObjectsByGroup", "SelectedObjects", "UnselectAllObjects",
        "LastCreatedObjects",
        # View
        "ZoomExtents", "ZoomSelected", "ViewCamera", "ViewCameraTarget",
        "CurrentView", "ViewDisplayMode", "Redraw", "EnableRedraw",
        # Document
        "UnitSystem", "UnitAbsoluteTolerance", "DocumentName",
        # Mesh
        "AddMesh", "MeshBooleanUnion", "MeshBooleanDifference",
        "MeshBooleanIntersection", "JoinMeshes", "MeshToNurb",
        "IsMesh", "MeshVertices", "MeshFaces", "MeshArea", "MeshVolume",
        # Utility
        "Distance", "Angle", "CullDuplicatePoints", "SortPointList",
        # Transformation
        "XformScale", "XformRotation1", "XformMirror", "XformTranslation",
        # Group
        "AddGroup", "AddObjectsToGroup", "DeleteGroup", "GroupNames",
        # Material
        "AddMaterialToLayer", "AddMaterialToObject", "MaterialColor",
        "MaterialName",
        # Block
        "AddBlock", "InsertBlock", "ExplodeBlockInstance", "BlockNames",
        "IsBlockInstance",
        # Dimension
        "AddLinearDimension", "AddAlignedDimension", "AddLeader",
        # Plane
        "PlaneFromNormal", "PlaneFromPoints", "WorldXYPlane",
        # Userdata
        "SetUserText", "GetUserText", "SetDocumentUserText", "GetDocumentUserText",
    }

    def _rs_dispatch(self, function_name: str, args: List = None, kwargs: Dict = None) -> str:
        """Send a rhinoscript_dispatch command to Rhino."""
        result = get_rhino_connection().send_command("rhinoscript_dispatch", {
            "function_name": function_name,
            "args": args or [],
            "kwargs": kwargs or {},
        })
        return json.dumps(result, indent=2)

    def _register_individual_rs_tools(self):
        """Register individual MCP tools for high-frequency rs.* functions."""

        # -- Curve creation --

        def rs_AddLine(ctx: Context, start: List[float], end: List[float]) -> str:
            """Add a line curve between two 3D points. Returns the curve GUID."""
            return self._rs_dispatch("AddLine", [start, end])
        self.app.tool()(rs_AddLine)

        def rs_AddPolyline(ctx: Context, points: List[List[float]]) -> str:
            """Add a polyline through a list of 3D points. Returns the curve GUID."""
            return self._rs_dispatch("AddPolyline", [points])
        self.app.tool()(rs_AddPolyline)

        def rs_AddCircle(ctx: Context, center_or_plane: List[float], radius: float) -> str:
            """Add a circle. center_or_plane is [x,y,z]. Returns the curve GUID."""
            return self._rs_dispatch("AddCircle", [center_or_plane, radius])
        self.app.tool()(rs_AddCircle)

        def rs_AddArc3Pt(ctx: Context, start: List[float], end: List[float], point_on_arc: List[float]) -> str:
            """Add an arc through three points. Returns the curve GUID."""
            return self._rs_dispatch("AddArc3Pt", [start, end, point_on_arc])
        self.app.tool()(rs_AddArc3Pt)

        def rs_AddEllipse(ctx: Context, plane: List[float], rx: float, ry: float) -> str:
            """Add an ellipse. plane can be a point [x,y,z] for WorldXY at that origin. Returns curve GUID."""
            return self._rs_dispatch("AddEllipse", [plane, rx, ry])
        self.app.tool()(rs_AddEllipse)

        def rs_AddInterpCurve(ctx: Context, points: List[List[float]], degree: int = 3) -> str:
            """Add an interpolated curve through points. Returns the curve GUID."""
            return self._rs_dispatch("AddInterpCurve", [points, degree])
        self.app.tool()(rs_AddInterpCurve)

        def rs_AddNurbsCurve(ctx: Context, points: List[List[float]], knots: List[float], degree: int, weights: Optional[List[float]] = None) -> str:
            """Add a NURBS curve from control points, knots, and degree. Returns curve GUID."""
            args = [points, knots, degree]
            if weights:
                args.append(weights)
            return self._rs_dispatch("AddNurbsCurve", args)
        self.app.tool()(rs_AddNurbsCurve)

        def rs_AddRectangle(ctx: Context, plane: List[float], width: float, height: float) -> str:
            """Add a rectangular polyline. plane can be [x,y,z] for WorldXY at that point. Returns curve GUID."""
            return self._rs_dispatch("AddRectangle", [plane, width, height])
        self.app.tool()(rs_AddRectangle)

        def rs_AddSpiral(ctx: Context, point0: List[float], point1: List[float], pitch: float, turns: float, radius0: float, radius1: Optional[float] = None) -> str:
            """Add a spiral curve. Returns the curve GUID."""
            args = [point0, point1, pitch, turns, radius0]
            if radius1 is not None:
                args.append(radius1)
            return self._rs_dispatch("AddSpiral", args)
        self.app.tool()(rs_AddSpiral)

        def rs_AddBlendCurve(ctx: Context, curves: List[str], parameters: List[float], reverses: List[bool], continuities: List[int]) -> str:
            """Add a blend curve between two curves. Returns the curve GUID."""
            return self._rs_dispatch("AddBlendCurve", [curves, parameters, reverses, continuities])
        self.app.tool()(rs_AddBlendCurve)

        def rs_AddFilletCurve(ctx: Context, curve0: str, curve1: str, radius: float = 1.0, base_point0: Optional[List[float]] = None, base_point1: Optional[List[float]] = None) -> str:
            """Add a fillet curve between two curves. Returns the curve GUID."""
            args = [curve0, curve1, radius]
            if base_point0:
                args.append(base_point0)
            if base_point1:
                args.append(base_point1)
            return self._rs_dispatch("AddFilletCurve", args)
        self.app.tool()(rs_AddFilletCurve)

        # -- Curve query --

        def rs_CurveLength(ctx: Context, curve_id: str) -> str:
            """Return the length of a curve."""
            return self._rs_dispatch("CurveLength", [curve_id])
        self.app.tool()(rs_CurveLength)

        def rs_CurveStartPoint(ctx: Context, curve_id: str) -> str:
            """Return the start point of a curve as [x,y,z]."""
            return self._rs_dispatch("CurveStartPoint", [curve_id])
        self.app.tool()(rs_CurveStartPoint)

        def rs_CurveEndPoint(ctx: Context, curve_id: str) -> str:
            """Return the end point of a curve as [x,y,z]."""
            return self._rs_dispatch("CurveEndPoint", [curve_id])
        self.app.tool()(rs_CurveEndPoint)

        def rs_CurveMidPoint(ctx: Context, curve_id: str) -> str:
            """Return the midpoint of a curve as [x,y,z]."""
            return self._rs_dispatch("CurveMidPoint", [curve_id])
        self.app.tool()(rs_CurveMidPoint)

        def rs_CurveClosestPoint(ctx: Context, curve_id: str, test_point: List[float]) -> str:
            """Return the parameter of the closest point on a curve to a test point."""
            return self._rs_dispatch("CurveClosestPoint", [curve_id, test_point])
        self.app.tool()(rs_CurveClosestPoint)

        def rs_CurveDomain(ctx: Context, curve_id: str) -> str:
            """Return the domain [t0, t1] of a curve."""
            return self._rs_dispatch("CurveDomain", [curve_id])
        self.app.tool()(rs_CurveDomain)

        def rs_CurveArea(ctx: Context, curve_id: str) -> str:
            """Return the area of a closed planar curve."""
            return self._rs_dispatch("CurveArea", [curve_id])
        self.app.tool()(rs_CurveArea)

        def rs_CurveTangent(ctx: Context, curve_id: str, parameter: float) -> str:
            """Return the tangent vector at a parameter on a curve."""
            return self._rs_dispatch("CurveTangent", [curve_id, parameter])
        self.app.tool()(rs_CurveTangent)

        def rs_IsCurve(ctx: Context, object_id: str) -> str:
            """Test if an object is a curve."""
            return self._rs_dispatch("IsCurve", [object_id])
        self.app.tool()(rs_IsCurve)

        def rs_IsCurveClosed(ctx: Context, curve_id: str) -> str:
            """Test if a curve is closed."""
            return self._rs_dispatch("IsCurveClosed", [curve_id])
        self.app.tool()(rs_IsCurveClosed)

        # -- Curve operations --

        def rs_DivideCurve(ctx: Context, curve_id: str, segments: int, create_points: bool = False) -> str:
            """Divide a curve into segments. Returns list of points."""
            return self._rs_dispatch("DivideCurve", [curve_id, segments, create_points])
        self.app.tool()(rs_DivideCurve)

        def rs_EvaluateCurve(ctx: Context, curve_id: str, parameter: float) -> str:
            """Evaluate a curve at a parameter value. Returns [x,y,z]."""
            return self._rs_dispatch("EvaluateCurve", [curve_id, parameter])
        self.app.tool()(rs_EvaluateCurve)

        def rs_OffsetCurve(ctx: Context, curve_id: str, direction: List[float], distance: float) -> str:
            """Offset a curve. direction is a point indicating offset side. Returns list of curve GUIDs."""
            return self._rs_dispatch("OffsetCurve", [curve_id, direction, distance])
        self.app.tool()(rs_OffsetCurve)

        def rs_JoinCurves(ctx: Context, curve_ids: List[str], delete_input: bool = False) -> str:
            """Join multiple curves into polycurves. Returns list of joined curve GUIDs."""
            return self._rs_dispatch("JoinCurves", [curve_ids, delete_input])
        self.app.tool()(rs_JoinCurves)

        def rs_ExplodeCurves(ctx: Context, curve_ids: List[str], delete_input: bool = False) -> str:
            """Explode polycurves into segment curves. Returns list of curve GUIDs."""
            return self._rs_dispatch("ExplodeCurves", [curve_ids, delete_input])
        self.app.tool()(rs_ExplodeCurves)

        def rs_SplitCurve(ctx: Context, curve_id: str, parameters: List[float], delete_input: bool = True) -> str:
            """Split a curve at parameters. Returns list of new curve GUIDs."""
            return self._rs_dispatch("SplitCurve", [curve_id, parameters, delete_input])
        self.app.tool()(rs_SplitCurve)

        def rs_RebuildCurve(ctx: Context, curve_id: str, degree: int = 3, point_count: int = 10) -> str:
            """Rebuild a curve with specified degree and point count. Returns True on success."""
            return self._rs_dispatch("RebuildCurve", [curve_id, degree, point_count])
        self.app.tool()(rs_RebuildCurve)

        def rs_ReverseCurve(ctx: Context, curve_id: str) -> str:
            """Reverse the direction of a curve. Returns True on success."""
            return self._rs_dispatch("ReverseCurve", [curve_id])
        self.app.tool()(rs_ReverseCurve)

        def rs_CloseCurve(ctx: Context, curve_id: str, tolerance: float = -1.0) -> str:
            """Close an open curve. Returns the closed curve GUID."""
            return self._rs_dispatch("CloseCurve", [curve_id, tolerance])
        self.app.tool()(rs_CloseCurve)

        # -- Surface creation --

        def rs_AddSphere(ctx: Context, center_or_plane: List[float], radius: float) -> str:
            """Add a sphere. Returns the surface GUID."""
            return self._rs_dispatch("AddSphere", [center_or_plane, radius])
        self.app.tool()(rs_AddSphere)

        def rs_AddCylinder(ctx: Context, base: List[float], height: float, radius: float, cap: bool = True) -> str:
            """Add a cylinder. base is center of bottom [x,y,z]. Returns surface GUID."""
            return self._rs_dispatch("AddCylinder", [base, height, radius, cap])
        self.app.tool()(rs_AddCylinder)

        def rs_AddCone(ctx: Context, base: List[float], height: float, radius: float, cap: bool = True) -> str:
            """Add a cone. base is center of bottom [x,y,z]. Returns surface GUID."""
            return self._rs_dispatch("AddCone", [base, height, radius, cap])
        self.app.tool()(rs_AddCone)

        def rs_AddBox(ctx: Context, corners: List[List[float]]) -> str:
            """Add a box from 8 corner points. Returns the surface GUID."""
            return self._rs_dispatch("AddBox", [corners])
        self.app.tool()(rs_AddBox)

        def rs_AddTorus(ctx: Context, base: List[float], major_radius: float, minor_radius: float) -> str:
            """Add a torus. base is center [x,y,z]. Returns surface GUID."""
            return self._rs_dispatch("AddTorus", [base, major_radius, minor_radius])
        self.app.tool()(rs_AddTorus)

        def rs_AddPipe(ctx: Context, curve_id: str, parameters: List[float], radii: List[float], blend_type: int = 0, cap: int = 1, fit: bool = False) -> str:
            """Add pipe surfaces around a curve. Returns list of surface GUIDs."""
            return self._rs_dispatch("AddPipe", [curve_id, parameters, radii, blend_type, cap, fit])
        self.app.tool()(rs_AddPipe)

        def rs_AddPlanarSrf(ctx: Context, curve_ids: List[str]) -> str:
            """Create a planar surface from closed planar curves. Returns list of surface GUIDs."""
            return self._rs_dispatch("AddPlanarSrf", [curve_ids])
        self.app.tool()(rs_AddPlanarSrf)

        def rs_AddLoftSrf(ctx: Context, curve_ids: List[str], start: Optional[List[float]] = None, end: Optional[List[float]] = None, loft_type: int = 0, closed: bool = False) -> str:
            """Create a lofted surface through curves. loft_type: 0=Normal,1=Loose,2=Tight,3=Straight. Returns list of surface GUIDs."""
            args = [curve_ids]
            if start:
                args.append(start)
            else:
                args.append(None)
            if end:
                args.append(end)
            else:
                args.append(None)
            args.append(loft_type)
            args.append(closed)
            return self._rs_dispatch("AddLoftSrf", args)
        self.app.tool()(rs_AddLoftSrf)

        def rs_AddSweep1(ctx: Context, rail: str, shapes: List[str], closed: bool = False) -> str:
            """Create a sweep1 surface. Returns list of surface GUIDs."""
            return self._rs_dispatch("AddSweep1", [rail, shapes, closed])
        self.app.tool()(rs_AddSweep1)

        def rs_AddSweep2(ctx: Context, rails: List[str], shapes: List[str], closed: bool = False) -> str:
            """Create a sweep2 surface along two rails. Returns list of surface GUIDs."""
            return self._rs_dispatch("AddSweep2", [rails, shapes, closed])
        self.app.tool()(rs_AddSweep2)

        def rs_AddRevSrf(ctx: Context, curve_id: str, axis: List[List[float]], start_angle: float = 0.0, end_angle: float = 360.0) -> str:
            """Create a surface of revolution. axis is [[x,y,z],[x,y,z]]. Returns surface GUID."""
            return self._rs_dispatch("AddRevSrf", [curve_id, axis, start_angle, end_angle])
        self.app.tool()(rs_AddRevSrf)

        def rs_AddEdgeSrf(ctx: Context, curve_ids: List[str]) -> str:
            """Create a surface from 2, 3, or 4 edge curves. Returns surface GUID."""
            return self._rs_dispatch("AddEdgeSrf", [curve_ids])
        self.app.tool()(rs_AddEdgeSrf)

        def rs_AddNetworkSrf(ctx: Context, curve_ids: List[str]) -> str:
            """Create a surface from a network of crossing curves. Returns surface GUID."""
            return self._rs_dispatch("AddNetworkSrf", [curve_ids])
        self.app.tool()(rs_AddNetworkSrf)

        def rs_AddPatch(ctx: Context, object_ids: List[str], uv_spans_or_count: Optional[List[int]] = None) -> str:
            """Create a patch surface from curves/points. Returns surface GUID."""
            args = [object_ids]
            if uv_spans_or_count:
                args.extend(uv_spans_or_count)
            return self._rs_dispatch("AddPatch", args)
        self.app.tool()(rs_AddPatch)

        # -- Surface operations --

        def rs_ExtrudeCurveStraight(ctx: Context, curve_id: str, start_point: List[float], end_point: List[float]) -> str:
            """Extrude a curve straight between two points. Returns surface GUID."""
            return self._rs_dispatch("ExtrudeCurveStraight", [curve_id, start_point, end_point])
        self.app.tool()(rs_ExtrudeCurveStraight)

        def rs_CapPlanarHoles(ctx: Context, surface_id: str) -> str:
            """Cap all planar holes in a surface/polysurface. Returns True on success."""
            return self._rs_dispatch("CapPlanarHoles", [surface_id])
        self.app.tool()(rs_CapPlanarHoles)

        def rs_FilletSurfaces(ctx: Context, surface0: str, surface1: str, radius: float) -> str:
            """Create a fillet surface between two surfaces. Returns list of surface GUIDs."""
            return self._rs_dispatch("FilletSurfaces", [surface0, surface1, radius])
        self.app.tool()(rs_FilletSurfaces)

        def rs_OffsetSurface(ctx: Context, surface_id: str, distance: float) -> str:
            """Offset a surface by a distance. Returns surface GUID."""
            return self._rs_dispatch("OffsetSurface", [surface_id, distance])
        self.app.tool()(rs_OffsetSurface)

        def rs_JoinSurfaces(ctx: Context, surface_ids: List[str], delete_input: bool = False) -> str:
            """Join surfaces into polysurfaces. Returns the joined polysurface GUID."""
            return self._rs_dispatch("JoinSurfaces", [surface_ids, delete_input])
        self.app.tool()(rs_JoinSurfaces)

        def rs_ExplodePolysurfaces(ctx: Context, surface_ids: List[str], delete_input: bool = False) -> str:
            """Explode polysurfaces into individual surfaces. Returns list of surface GUIDs."""
            return self._rs_dispatch("ExplodePolysurfaces", [surface_ids, delete_input])
        self.app.tool()(rs_ExplodePolysurfaces)

        def rs_DuplicateEdgeCurves(ctx: Context, surface_id: str, select: bool = False) -> str:
            """Duplicate the edge curves of a surface. Returns list of curve GUIDs."""
            return self._rs_dispatch("DuplicateEdgeCurves", [surface_id, select])
        self.app.tool()(rs_DuplicateEdgeCurves)

        def rs_DuplicateSurfaceBorder(ctx: Context, surface_id: str) -> str:
            """Duplicate the border of a surface. Returns list of curve GUIDs."""
            return self._rs_dispatch("DuplicateSurfaceBorder", [surface_id])
        self.app.tool()(rs_DuplicateSurfaceBorder)

        def rs_ExtractIsoCurve(ctx: Context, surface_id: str, parameter: List[float], direction: int) -> str:
            """Extract an isocurve from a surface. direction: 0=U, 1=V. Returns list of curve GUIDs."""
            return self._rs_dispatch("ExtractIsoCurve", [surface_id, parameter, direction])
        self.app.tool()(rs_ExtractIsoCurve)

        # -- Surface query --

        def rs_SurfaceArea(ctx: Context, surface_id: str) -> str:
            """Return the area of a surface or polysurface."""
            return self._rs_dispatch("SurfaceArea", [surface_id])
        self.app.tool()(rs_SurfaceArea)

        def rs_SurfaceVolume(ctx: Context, surface_id: str) -> str:
            """Return the volume of a closed surface or polysurface."""
            return self._rs_dispatch("SurfaceVolume", [surface_id])
        self.app.tool()(rs_SurfaceVolume)

        def rs_SurfaceNormal(ctx: Context, surface_id: str, uv_parameter: List[float]) -> str:
            """Return the normal direction at a uv parameter on a surface."""
            return self._rs_dispatch("SurfaceNormal", [surface_id, uv_parameter])
        self.app.tool()(rs_SurfaceNormal)

        def rs_SurfaceDomain(ctx: Context, surface_id: str, direction: int) -> str:
            """Return the domain of a surface in a direction (0=U, 1=V)."""
            return self._rs_dispatch("SurfaceDomain", [surface_id, direction])
        self.app.tool()(rs_SurfaceDomain)

        def rs_EvaluateSurface(ctx: Context, surface_id: str, u: float, v: float) -> str:
            """Evaluate a surface at a UV parameter. Returns [x,y,z]."""
            return self._rs_dispatch("EvaluateSurface", [surface_id, u, v])
        self.app.tool()(rs_EvaluateSurface)

        def rs_BrepClosestPoint(ctx: Context, surface_id: str, point: List[float]) -> str:
            """Find the closest point on a brep to a test point."""
            return self._rs_dispatch("BrepClosestPoint", [surface_id, point])
        self.app.tool()(rs_BrepClosestPoint)

        def rs_IsSurface(ctx: Context, object_id: str) -> str:
            """Test if an object is a surface."""
            return self._rs_dispatch("IsSurface", [object_id])
        self.app.tool()(rs_IsSurface)

        def rs_IsPolysurface(ctx: Context, object_id: str) -> str:
            """Test if an object is a polysurface."""
            return self._rs_dispatch("IsPolysurface", [object_id])
        self.app.tool()(rs_IsPolysurface)

        def rs_IsPolysurfaceClosed(ctx: Context, object_id: str) -> str:
            """Test if a polysurface is closed (solid)."""
            return self._rs_dispatch("IsPolysurfaceClosed", [object_id])
        self.app.tool()(rs_IsPolysurfaceClosed)

        # -- Object operations --

        def rs_CopyObject(ctx: Context, object_id: str, translation: Optional[List[float]] = None) -> str:
            """Copy an object with optional translation [x,y,z]. Returns new object GUID."""
            args = [object_id]
            if translation:
                args.append(translation)
            return self._rs_dispatch("CopyObject", args)
        self.app.tool()(rs_CopyObject)

        def rs_MoveObject(ctx: Context, object_id: str, translation: List[float]) -> str:
            """Move an object by a translation vector [x,y,z]. Returns the object GUID."""
            return self._rs_dispatch("MoveObject", [object_id, translation])
        self.app.tool()(rs_MoveObject)

        def rs_RotateObject(ctx: Context, object_id: str, center_point: List[float], rotation_angle: float, axis: Optional[List[float]] = None) -> str:
            """Rotate an object around a center point by degrees. Optional axis for 3D rotation. Returns GUID."""
            args = [object_id, center_point, rotation_angle]
            if axis:
                args.append(axis)
            return self._rs_dispatch("RotateObject", args)
        self.app.tool()(rs_RotateObject)

        def rs_ScaleObject(ctx: Context, object_id: str, origin: List[float], scale: List[float]) -> str:
            """Scale an object from an origin point. scale is [sx,sy,sz]. Returns GUID."""
            return self._rs_dispatch("ScaleObject", [object_id, origin, scale])
        self.app.tool()(rs_ScaleObject)

        def rs_MirrorObject(ctx: Context, object_id: str, start_point: List[float], end_point: List[float], copy: bool = False) -> str:
            """Mirror an object across a line defined by two points. Returns GUID."""
            return self._rs_dispatch("MirrorObject", [object_id, start_point, end_point, copy])
        self.app.tool()(rs_MirrorObject)

        def rs_ObjectLayer(ctx: Context, object_id: str, layer: Optional[str] = None) -> str:
            """Get or set the layer of an object. If layer is None, returns current layer name."""
            args = [object_id]
            if layer is not None:
                args.append(layer)
            return self._rs_dispatch("ObjectLayer", args)
        self.app.tool()(rs_ObjectLayer)

        def rs_ObjectName(ctx: Context, object_id: str, name: Optional[str] = None) -> str:
            """Get or set the name of an object."""
            args = [object_id]
            if name is not None:
                args.append(name)
            return self._rs_dispatch("ObjectName", args)
        self.app.tool()(rs_ObjectName)

        def rs_ObjectColor(ctx: Context, object_id: str, color: Optional[List[int]] = None) -> str:
            """Get or set the display color of an object. color is [r,g,b]."""
            args = [object_id]
            if color is not None:
                args.append(color)
            return self._rs_dispatch("ObjectColor", args)
        self.app.tool()(rs_ObjectColor)

        def rs_ObjectType(ctx: Context, object_id: str) -> str:
            """Return the object type as an integer."""
            return self._rs_dispatch("ObjectType", [object_id])
        self.app.tool()(rs_ObjectType)

        # -- Geometry --

        def rs_AddPoint(ctx: Context, point: List[float]) -> str:
            """Add a point object at [x,y,z]. Returns the point GUID."""
            return self._rs_dispatch("AddPoint", [point])
        self.app.tool()(rs_AddPoint)

        def rs_AddPoints(ctx: Context, points: List[List[float]]) -> str:
            """Add multiple point objects. Returns list of point GUIDs."""
            return self._rs_dispatch("AddPoints", [points])
        self.app.tool()(rs_AddPoints)

        def rs_AddTextDot(ctx: Context, text: str, point: List[float]) -> str:
            """Add a text dot at a 3D point. Returns GUID."""
            return self._rs_dispatch("AddTextDot", [text, point])
        self.app.tool()(rs_AddTextDot)

        def rs_AddText(ctx: Context, text: str, point_or_plane: List[float], height: float = 1.0, font: Optional[str] = None, font_style: int = 0) -> str:
            """Add text to the document. Returns GUID."""
            args = [text, point_or_plane, height]
            if font:
                args.append(font)
                args.append(font_style)
            return self._rs_dispatch("AddText", args)
        self.app.tool()(rs_AddText)

        def rs_BoundingBox(ctx: Context, object_ids: List[str]) -> str:
            """Return the bounding box of one or more objects as 8 corner points."""
            return self._rs_dispatch("BoundingBox", [object_ids])
        self.app.tool()(rs_BoundingBox)

        def rs_Area(ctx: Context, object_id: str) -> str:
            """Return the area of a closed curve, surface, or mesh."""
            return self._rs_dispatch("Area", [object_id])
        self.app.tool()(rs_Area)

        def rs_PointCoordinates(ctx: Context, point_id: str) -> str:
            """Return the 3D coordinates of a point object."""
            return self._rs_dispatch("PointCoordinates", [point_id])
        self.app.tool()(rs_PointCoordinates)

        # -- Selection --

        def rs_AllObjects(ctx: Context, select: bool = False, include_lights: bool = False) -> str:
            """Return all object GUIDs in the document."""
            return self._rs_dispatch("AllObjects", [select, include_lights])
        self.app.tool()(rs_AllObjects)

        def rs_ObjectsByLayer(ctx: Context, layer_name: str, select: bool = False) -> str:
            """Return all objects on a specific layer."""
            return self._rs_dispatch("ObjectsByLayer", [layer_name, select])
        self.app.tool()(rs_ObjectsByLayer)

        def rs_ObjectsByType(ctx: Context, geometry_type: int, select: bool = False) -> str:
            """Return all objects of a given type. Types: 1=Point, 4=Curve, 8=Surface, 16=Polysurface, 32=Mesh."""
            return self._rs_dispatch("ObjectsByType", [geometry_type, select])
        self.app.tool()(rs_ObjectsByType)

        def rs_ObjectsByName(ctx: Context, name: str, select: bool = False) -> str:
            """Return all objects with a given name."""
            return self._rs_dispatch("ObjectsByName", [name, select])
        self.app.tool()(rs_ObjectsByName)

        def rs_SelectedObjects(ctx: Context) -> str:
            """Return GUIDs of all currently selected objects."""
            return self._rs_dispatch("SelectedObjects")
        self.app.tool()(rs_SelectedObjects)

        def rs_UnselectAllObjects(ctx: Context) -> str:
            """Unselect all objects in the document."""
            return self._rs_dispatch("UnselectAllObjects")
        self.app.tool()(rs_UnselectAllObjects)

        def rs_LastCreatedObjects(ctx: Context, select: bool = False) -> str:
            """Return the GUIDs of the last objects created."""
            return self._rs_dispatch("LastCreatedObjects", [select])
        self.app.tool()(rs_LastCreatedObjects)

        # -- Layer --

        def rs_AddLayer(ctx: Context, name: str, color: Optional[List[int]] = None, visible: bool = True, locked: bool = False, parent: Optional[str] = None) -> str:
            """Add a new layer. Returns the layer index."""
            args = [name]
            if color:
                args.append(color)
            else:
                args.append(None)
            args.append(visible)
            args.append(locked)
            if parent:
                args.append(parent)
            return self._rs_dispatch("AddLayer", args)
        self.app.tool()(rs_AddLayer)

        def rs_CurrentLayer(ctx: Context, layer: Optional[str] = None) -> str:
            """Get or set the current layer name."""
            args = []
            if layer is not None:
                args.append(layer)
            return self._rs_dispatch("CurrentLayer", args)
        self.app.tool()(rs_CurrentLayer)

        def rs_LayerVisible(ctx: Context, layer_name: str, visible: Optional[bool] = None) -> str:
            """Get or set layer visibility."""
            args = [layer_name]
            if visible is not None:
                args.append(visible)
            return self._rs_dispatch("LayerVisible", args)
        self.app.tool()(rs_LayerVisible)

        def rs_LayerColor(ctx: Context, layer_name: str, color: Optional[List[int]] = None) -> str:
            """Get or set the color of a layer."""
            args = [layer_name]
            if color is not None:
                args.append(color)
            return self._rs_dispatch("LayerColor", args)
        self.app.tool()(rs_LayerColor)

        def rs_LayerNames(ctx: Context) -> str:
            """Return all layer names in the document."""
            return self._rs_dispatch("LayerNames")
        self.app.tool()(rs_LayerNames)

        def rs_RenameLayer(ctx: Context, old_name: str, new_name: str) -> str:
            """Rename a layer. Returns the new name on success."""
            return self._rs_dispatch("RenameLayer", [old_name, new_name])
        self.app.tool()(rs_RenameLayer)

        # -- View --

        def rs_ZoomExtents(ctx: Context, view: Optional[str] = None, all_views: bool = False) -> str:
            """Zoom to fit all objects in the viewport."""
            args = [view, all_views]
            return self._rs_dispatch("ZoomExtents", args)
        self.app.tool()(rs_ZoomExtents)

        def rs_ZoomSelected(ctx: Context, view: Optional[str] = None, all_views: bool = False) -> str:
            """Zoom to fit selected objects."""
            args = [view, all_views]
            return self._rs_dispatch("ZoomSelected", args)
        self.app.tool()(rs_ZoomSelected)

        def rs_ViewCamera(ctx: Context, view: Optional[str] = None, camera: Optional[List[float]] = None) -> str:
            """Get or set the camera position of a view."""
            args = [view]
            if camera is not None:
                args.append(camera)
            return self._rs_dispatch("ViewCamera", args)
        self.app.tool()(rs_ViewCamera)

        def rs_CurrentView(ctx: Context, view: Optional[str] = None) -> str:
            """Get or set the current active view by name."""
            args = []
            if view is not None:
                args.append(view)
            return self._rs_dispatch("CurrentView", args)
        self.app.tool()(rs_CurrentView)

        def rs_Redraw(ctx: Context) -> str:
            """Force a redraw of all views."""
            return self._rs_dispatch("Redraw")
        self.app.tool()(rs_Redraw)

        def rs_EnableRedraw(ctx: Context, enable: bool = True) -> str:
            """Enable or disable viewport redraw for performance."""
            return self._rs_dispatch("EnableRedraw", [enable])
        self.app.tool()(rs_EnableRedraw)

        # -- Document --

        def rs_UnitSystem(ctx: Context, unit_system: Optional[int] = None) -> str:
            """Get or set the document unit system. Common: 2=mm, 3=cm, 4=m, 8=inches, 9=feet."""
            args = []
            if unit_system is not None:
                args.append(unit_system)
            return self._rs_dispatch("UnitSystem", args)
        self.app.tool()(rs_UnitSystem)

        def rs_DocumentName(ctx: Context) -> str:
            """Return the name of the current document."""
            return self._rs_dispatch("DocumentName")
        self.app.tool()(rs_DocumentName)

        # -- Mesh --

        def rs_AddMesh(ctx: Context, vertices: List[List[float]], face_vertices: List[List[int]]) -> str:
            """Add a mesh from vertices and face vertex indices. Returns mesh GUID."""
            return self._rs_dispatch("AddMesh", [vertices, face_vertices])
        self.app.tool()(rs_AddMesh)

        def rs_MeshBooleanUnion(ctx: Context, mesh_ids: List[str]) -> str:
            """Boolean union of meshes. Returns list of mesh GUIDs."""
            return self._rs_dispatch("MeshBooleanUnion", [mesh_ids])
        self.app.tool()(rs_MeshBooleanUnion)

        def rs_MeshBooleanDifference(ctx: Context, input0: List[str], input1: List[str]) -> str:
            """Boolean difference of meshes. Returns list of mesh GUIDs."""
            return self._rs_dispatch("MeshBooleanDifference", [input0, input1])
        self.app.tool()(rs_MeshBooleanDifference)

        def rs_JoinMeshes(ctx: Context, mesh_ids: List[str], delete_input: bool = False) -> str:
            """Join meshes into a single mesh. Returns the joined mesh GUID."""
            return self._rs_dispatch("JoinMeshes", [mesh_ids, delete_input])
        self.app.tool()(rs_JoinMeshes)

        def rs_MeshToNurb(ctx: Context, mesh_id: str) -> str:
            """Convert a mesh to a NURBS polysurface. Returns polysurface GUID."""
            return self._rs_dispatch("MeshToNurb", [mesh_id])
        self.app.tool()(rs_MeshToNurb)

        def rs_IsMesh(ctx: Context, object_id: str) -> str:
            """Test if an object is a mesh."""
            return self._rs_dispatch("IsMesh", [object_id])
        self.app.tool()(rs_IsMesh)

        # -- Utility --

        def rs_Distance(ctx: Context, point1: List[float], point2: List[float]) -> str:
            """Return the distance between two 3D points."""
            return self._rs_dispatch("Distance", [point1, point2])
        self.app.tool()(rs_Distance)

        def rs_Angle(ctx: Context, point1: List[float], point2: List[float]) -> str:
            """Return the angle between two points (in degrees)."""
            return self._rs_dispatch("Angle", [point1, point2])
        self.app.tool()(rs_Angle)

        def rs_CullDuplicatePoints(ctx: Context, points: List[List[float]], tolerance: float = 0.01) -> str:
            """Remove duplicate points from a list. Returns culled point list."""
            return self._rs_dispatch("CullDuplicatePoints", [points, tolerance])
        self.app.tool()(rs_CullDuplicatePoints)

        # -- Transformation --

        def rs_XformScale(ctx: Context, scale: List[float], point: Optional[List[float]] = None) -> str:
            """Create a scale transformation matrix. Use with rs_TransformObject."""
            args = [scale]
            if point:
                args.append(point)
            return self._rs_dispatch("XformScale", args)
        self.app.tool()(rs_XformScale)

        def rs_XformTranslation(ctx: Context, vector: List[float]) -> str:
            """Create a translation transformation matrix."""
            return self._rs_dispatch("XformTranslation", [vector])
        self.app.tool()(rs_XformTranslation)

        def rs_TransformObject(ctx: Context, object_id: str, matrix: List[List[float]], copy: bool = False) -> str:
            """Transform an object with a 4x4 transformation matrix. Returns GUID."""
            return self._rs_dispatch("TransformObject", [object_id, matrix, copy])
        self.app.tool()(rs_TransformObject)

        # -- Group --

        def rs_AddGroup(ctx: Context, group_name: Optional[str] = None) -> str:
            """Add a new empty group. Returns the group name."""
            args = []
            if group_name:
                args.append(group_name)
            return self._rs_dispatch("AddGroup", args)
        self.app.tool()(rs_AddGroup)

        def rs_AddObjectsToGroup(ctx: Context, object_ids: List[str], group_name: str) -> str:
            """Add objects to a group. Returns count of objects added."""
            return self._rs_dispatch("AddObjectsToGroup", [object_ids, group_name])
        self.app.tool()(rs_AddObjectsToGroup)

        def rs_GroupNames(ctx: Context) -> str:
            """Return all group names in the document."""
            return self._rs_dispatch("GroupNames")
        self.app.tool()(rs_GroupNames)

        # -- Material --

        def rs_AddMaterialToObject(ctx: Context, object_id: str) -> str:
            """Add a material to an object. Returns the material index."""
            return self._rs_dispatch("AddMaterialToObject", [object_id])
        self.app.tool()(rs_AddMaterialToObject)

        def rs_MaterialColor(ctx: Context, material_index: int, color: Optional[List[int]] = None) -> str:
            """Get or set the diffuse color of a material. color is [r,g,b]."""
            args = [material_index]
            if color is not None:
                args.append(color)
            return self._rs_dispatch("MaterialColor", args)
        self.app.tool()(rs_MaterialColor)

        # -- Block --

        def rs_InsertBlock(ctx: Context, block_name: str, insertion_point: List[float], scale: Optional[List[float]] = None, angle: float = 0.0) -> str:
            """Insert a block instance. Returns the instance GUID."""
            args = [block_name, insertion_point]
            if scale:
                args.append(scale)
            else:
                args.append([1, 1, 1])
            args.append(angle)
            return self._rs_dispatch("InsertBlock", args)
        self.app.tool()(rs_InsertBlock)

        def rs_ExplodeBlockInstance(ctx: Context, block_id: str, delete_input: bool = True) -> str:
            """Explode a block instance into individual objects. Returns list of object GUIDs."""
            return self._rs_dispatch("ExplodeBlockInstance", [block_id, delete_input])
        self.app.tool()(rs_ExplodeBlockInstance)

        def rs_BlockNames(ctx: Context) -> str:
            """Return all block definition names."""
            return self._rs_dispatch("BlockNames")
        self.app.tool()(rs_BlockNames)

        # -- Plane --

        def rs_PlaneFromNormal(ctx: Context, origin: List[float], normal: List[float]) -> str:
            """Create a plane from an origin and normal vector."""
            return self._rs_dispatch("PlaneFromNormal", [origin, normal])
        self.app.tool()(rs_PlaneFromNormal)

        def rs_PlaneFromPoints(ctx: Context, origin: List[float], x_point: List[float], y_point: List[float]) -> str:
            """Create a plane from three points."""
            return self._rs_dispatch("PlaneFromPoints", [origin, x_point, y_point])
        self.app.tool()(rs_PlaneFromPoints)

        def rs_WorldXYPlane(ctx: Context) -> str:
            """Return the world XY plane."""
            return self._rs_dispatch("WorldXYPlane")
        self.app.tool()(rs_WorldXYPlane)

        # -- Userdata --

        def rs_SetUserText(ctx: Context, object_id: str, key: str, value: Optional[str] = None) -> str:
            """Set a user text key-value pair on an object. Pass value=None to delete."""
            args = [object_id, key]
            if value is not None:
                args.append(value)
            return self._rs_dispatch("SetUserText", args)
        self.app.tool()(rs_SetUserText)

        def rs_GetUserText(ctx: Context, object_id: str, key: Optional[str] = None) -> str:
            """Get user text from an object. If key is None, returns all keys."""
            args = [object_id]
            if key is not None:
                args.append(key)
            return self._rs_dispatch("GetUserText", args)
        self.app.tool()(rs_GetUserText)

        # -- Dimension --

        def rs_AddLinearDimension(ctx: Context, start: List[float], end: List[float], text_point: List[float]) -> str:
            """Add a linear dimension. Returns the dimension GUID."""
            return self._rs_dispatch("AddLinearDimension", [start, end, text_point])
        self.app.tool()(rs_AddLinearDimension)

        def rs_AddLeader(ctx: Context, points: List[List[float]], text: Optional[str] = None) -> str:
            """Add a leader annotation. Returns the leader GUID."""
            args = [points]
            if text:
                args.append(text)
            return self._rs_dispatch("AddLeader", args)
        self.app.tool()(rs_AddLeader)

    # ------------------------------------------------------------------
    # Category-level catch-all tools (one tool per RS category)
    # ------------------------------------------------------------------

    # Map of category -> short description for the tool docstring
    _CATEGORY_DESCRIPTIONS = {
        "application": "Rhino application settings, aliases, search paths, and status bar functions",
        "block": "Block definitions and instances — create, insert, explode, query blocks",
        "curve": "Curve creation, query, and manipulation — arcs, circles, NURBS, offsets, booleans, etc.",
        "dimension": "Dimensions, leaders, and dimension styles",
        "document": "Document properties — units, tolerances, render settings, file info",
        "geometry": "Points, text dots, text objects, point clouds, clipping planes, and area/bounding box queries",
        "grips": "Control point grip editing — enable, select, move grips",
        "group": "Object groups — create, add to, remove, query",
        "hatch": "Hatch patterns and hatch objects",
        "layer": "Layer management — create, delete, visibility, color, locking",
        "light": "Lights — directional, point, spot, rectangular, linear",
        "line": "Line intersection and distance calculations",
        "linetype": "Linetype queries",
        "material": "Materials — create, assign to objects/layers, modify properties",
        "mesh": "Mesh creation, booleans, queries, and conversion",
        "object": "Object manipulation — copy, move, rotate, scale, mirror, properties",
        "plane": "Plane construction, intersection, and evaluation",
        "pointvector": "Point and vector math — add, subtract, cross product, transform",
        "selection": "Object selection and filtering by layer, type, name, color",
        "surface": "Surface/polysurface creation, booleans, filleting, offsetting, queries",
        "toolbar": "Toolbar management",
        "transformation": "Transformation matrices — scale, rotate, translate, mirror, shear",
        "userdata": "User text and document data — get/set key-value metadata",
        "userinterface": "UI dialogs — get user input, message boxes, file dialogs",
        "utility": "Utility functions — distance, angle, color, sorting, point creation",
        "view": "Viewport control — zoom, camera, display modes, named views, CPlanes",
    }

    def _register_category_tools(self):
        """Register one catch-all tool per RhinoScriptSyntax category."""
        categories = get_categories()
        for cat in categories:
            self._make_category_tool(cat)

    def _make_category_tool(self, category: str):
        """Create and register a single category-level dispatch tool."""
        # Get all functions in this category
        all_funcs = [f["function_name"] for f in get_all_functions(category=category)]
        # Exclude individually-registered functions
        remaining = [f for f in all_funcs if f not in self.INDIVIDUAL_RS_FUNCTIONS]

        if not remaining:
            return  # All functions in this category have individual tools

        desc = self._CATEGORY_DESCRIPTIONS.get(category, "RhinoScriptSyntax {0} functions".format(category))
        func_list = ", ".join(sorted(remaining))

        # Build the tool function
        tool_self = self  # capture for closure

        async def category_handler(
            ctx: Context,
            function_name: str,
            args: Optional[List] = None,
            kwargs: Optional[Dict[str, Any]] = None,
        ) -> str:
            """placeholder"""
            return tool_self._rs_dispatch(function_name, args, kwargs)

        # Set dynamic name and docstring
        tool_name = "rhinoscript_{0}".format(category)
        category_handler.__name__ = tool_name
        category_handler.__qualname__ = "RhinoTools.{0}".format(tool_name)
        category_handler.__doc__ = (
            "{0}.\n\n"
            "Call any rs.* function in the '{1}' category by name.\n"
            "Use look_up_RhinoScriptSyntax(function_name) for detailed parameter docs.\n\n"
            "Available functions: {2}"
        ).format(desc, category, func_list)

        self.app.tool()(category_handler)

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
        # Generate short ID with milliseconds to avoid collisions
        _now = datetime.now()
        short_id = _now.strftime("%d%H%M%S") + "{0:03d}".format(_now.microsecond // 1000)
        
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
                return "Function '{0}' not found in RhinoScriptSyntax categories".format(function_name)

            # Construct the URL to the GitHub repository source code (Rhino 7 branch)
            github_url = "https://raw.githubusercontent.com/mcneel/rhinoscriptsyntax/rhino-7.x/Scripts/rhinoscript/{0}.py".format(category)
            logger.info("Looking up documentation at URL: {0}".format(github_url))

            # Fetch the Python source file
            response = requests.get(github_url)
            if response.status_code != 200:
                return "Failed to fetch source code for category '{0}' (HTTP status: {1})".format(category, response.status_code)

            # Parse the Python file to find the function definition and docstring
            source_code = response.text

            # Look for the function definition
            function_pattern = re.compile("def {0}\\s*\\(.*?\\):".format(function_name), re.DOTALL)
            function_match = function_pattern.search(source_code)
            if not function_match:
                return "Function '{0}' not found in the source code for category '{1}'".format(function_name, category)

            # Find the start of the function
            function_start = function_match.start()

            # Extract the docstring
            docstring_start = source_code.find('"""', function_start)
            if docstring_start == -1:
                return "No documentation found for function '{0}'".format(function_name)

            docstring_end = source_code.find('"""', docstring_start + 3)
            if docstring_end == -1:
                return "Malformed documentation for function '{0}'".format(function_name)

            docstring = source_code[docstring_start + 3:docstring_end].strip()

            # Format the docstring into Markdown
            documentation = []

            # Add the function name as a header
            documentation.append("# {0}".format(function_name))
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
                    documentation.append("## {0}".format(section))
                    for line in content:
                        if line:
                            documentation.append("- {0}".format(line))
                    documentation.append("")
                elif section == "Returns" and content:
                    documentation.append("## {0}".format(section))
                    for line in content:
                        if line:
                            documentation.append("- {0}".format(line))
                    documentation.append("")
                elif section == "Example" and content:
                    documentation.append("## {0}".format(section))
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
                    documentation.append("## {0}".format(section))
                    items = []
                    for line in content:
                        if line.strip():
                            items.append(line.strip())

                    for item in items:
                        documentation.append("- {0}".format(item))
                    documentation.append("")

            # Add a link to the GitHub repository
            github_view_url = "https://github.com/mcneel/rhinoscriptsyntax/blob/rhino-7.x/Scripts/rhinoscript/{0}.py".format(category)
            documentation.append("[View source code on GitHub]({0})".format(github_view_url))

            return "\n".join(documentation)

        except Exception as e:
            logger.error("Error looking up RhinoScriptSyntax documentation: {0}".format(str(e)))
            return "Error fetching documentation: {0}".format(str(e))