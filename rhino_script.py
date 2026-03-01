#! python3
"""
Rhino MCP - Rhino-side Script
Handles communication with external MCP server and executes Rhino commands.
"""

import socket
import threading
import json
import time
import System
import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs
import os
import platform
import traceback
import sys
import base64
from System.Drawing import Bitmap
from System.Drawing.Imaging import ImageFormat
from System.IO import MemoryStream
from datetime import datetime

# Grasshopper imports (will be available when Grasshopper is loaded)
try:
    from Grasshopper import Instances
    from Grasshopper.Kernel import GH_ComponentServer
    from System import Guid
    from System.Drawing import PointF
    # Import common Grasshopper component libraries
    import Grasshopper.Kernel.Parameters as Params
    import Grasshopper.Kernel.Special as Special
except ImportError:
    # Grasshopper not available, will be handled in functions
    Instances = None
    GH_ComponentServer = None
    Guid = None
    PointF = None
    Params = None
    Special = None

# Configuration
HOST = 'localhost'
PORT = 9876

# Add constant for annotation layer
ANNOTATION_LAYER = "MCP_Annotations"

VALID_METADATA_FIELDS = {
    'required': ['id', 'name', 'type', 'layer'],
    'optional': [
        'short_id',      # Short identifier (DDHHMMSS format)
        'created_at',    # Timestamp of creation
        'bbox',          # Bounding box coordinates
        'description',   # Object description
        'user_text'      # All user text key-value pairs
    ]
}

# Note: Component creation now uses dynamic lookup through Grasshopper's component server
# instead of hardcoded mappings. This is more robust and handles component name variations.

def get_log_dir():
    """Get the appropriate log directory based on the platform"""
    home_dir = os.path.expanduser("~")
    
    # Platform-specific log directory
    if platform.system() == "Darwin":  # macOS
        log_dir = os.path.join(home_dir, "Library", "Application Support", "RhinoMCP", "logs")
    elif platform.system() == "Windows":
        log_dir = os.path.join(home_dir, "AppData", "Local", "RhinoMCP", "logs")
    else:  # Linux and others
        log_dir = os.path.join(home_dir, ".rhino_mcp", "logs")
    
    return log_dir

def log_message(message):
    """Log a message to both Rhino's command line and log file"""
    # Print to Rhino's command line
    Rhino.RhinoApp.WriteLine(message)
    
    # Log to file
    try:
        log_dir = get_log_dir()
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(log_dir, "rhino_mcp.log")
        
        # Log platform info on first run
        if not os.path.exists(log_file):
            with open(log_file, "w") as f:
                f.write("=== RhinoMCP Log ===\n")
                f.write("Platform: {0}\n".format(platform.system()))
                f.write("Python Version: {0}\n".format(sys.version))
                f.write("Rhino Version: {0}\n".format(Rhino.RhinoApp.Version))
                f.write("==================\n\n")
        
        with open(log_file, "a") as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write("[{0}] {1}\n".format(timestamp, message))
    except Exception as e:
        Rhino.RhinoApp.WriteLine("Failed to write to log file: {0}".format(str(e)))

class RhinoMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        # Bind jewelry helper functions defined at module scope (IronPython-safe)
        try:
            self._ring_blank = _ring_blank.__get__(self, RhinoMCPServer)
            self._head_blank = _head_blank.__get__(self, RhinoMCPServer)
            self._section_profile = _section_profile.__get__(self, RhinoMCPServer)
            self._place_head_on_band = _place_head_on_band.__get__(self, RhinoMCPServer)
            self._edge_selector_presets = _edge_selector_presets.__get__(self, RhinoMCPServer)
            self._safe_boolean_union = _safe_boolean_union.__get__(self, RhinoMCPServer)
            self._safe_boolean_difference = _safe_boolean_difference.__get__(self, RhinoMCPServer)
            self._loft_sections = _loft_sections.__get__(self, RhinoMCPServer)
        except Exception as _bind_err:
            log_message("WARNING: failed binding jewelry helpers: {0}".format(str(_bind_err)))
    
    def start(self):
        if self.running:
            log_message("Server is already running on {0}:{1}".format(self.host, self.port))
            return
            
        self.running = True
        
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            
            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            log_message("RhinoMCP server started on {0}:{1}".format(self.host, self.port))
        except Exception as e:
            log_message("Failed to start server: {0}".format(str(e)))
            self.stop()
            
    def stop(self):
        self.running = False
        
        # Close socket
        if self.socket:
            try:
                self.socket.close()
            self._curve_domain = _curve_domain.__get__(self, RhinoMCPServer)
            self._trim_curve_by_fraction = _trim_curve_by_fraction.__get__(self, RhinoMCPServer)
except:
                pass
            self.socket = None
        
        # Wait for thread to finish
        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None
        
        log_message("RhinoMCP server stopped")
    
    def _server_loop(self):
        """Main server loop that accepts connections"""
        while self.running:
            try:
                client, addr = self.socket.accept()
                log_message("Client connected from {0}:{1}".format(addr[0], addr[1]))
                
                # Handle client in a new thread
                client_thread = threading.Thread(target=self._handle_client, args=(client,))
                client_thread.daemon = True
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    log_message("Error accepting connection: {0}".format(str(e)))
                    time.sleep(0.5)
    
    def _handle_client(self, client):
        """Handle a client connection"""
        try:
            # Set socket buffer size
            client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 14485760)  # 10MB
            client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 14485760)  # 10MB
            
            buffer = b""

            def _send_json(obj):
                try:
                    payload = (json.dumps(obj) + "\n").encode('utf-8')
                    client.sendall(payload)
                    return True
                except Exception as e:
                    log_message("Failed to send response: {0}".format(str(e)))
                    return False

            while self.running:
                data = client.recv(65536)
                if not data:
                    log_message("Client disconnected")
                    break

                buffer += data
                while b"\n" in buffer:
                    line, _, buffer = buffer.partition(b"\n")
                    if not line.strip():
                        continue

                    try:
                        command = json.loads(line.decode('utf-8'))
                        log_message("Received command: {0}".format(command))
                    except ValueError as e:
                        log_message("Invalid JSON received: {0}".format(str(e)))
                        if not _send_json({"status": "error", "message": "Invalid JSON format"}):
                            return
                        continue

                    # Execute on Rhino UI thread (Idle), but send response from a worker thread
                    def idle_handler(sender, e):
                        Rhino.RhinoApp.Idle -= idle_handler

                        def do_work():
                            try:
                                response = self.execute_command(command)
                            except Exception as ex:
                                log_message("Error executing command: {0}".format(str(ex)))
                                traceback.print_exc()
                                response = {"status": "error", "message": str(ex)}

                            if not _send_json(response):
                                try:
                                    client.close()
                                except:
                                    pass

                        # Execute the Rhino-side work on UI thread, but network send off-thread
                        try:
                            # IMPORTANT: execute_command touches Rhino doc, must run here
                            response = self.execute_command(command)
                            threading.Thread(target=lambda: _send_json(response), daemon=True).start()
                        except Exception as ex:
                            log_message("Error executing command: {0}".format(str(ex)))
                            traceback.print_exc()
                            threading.Thread(target=lambda: _send_json({"status": "error", "message": str(ex)}), daemon=True).start()

                    Rhino.RhinoApp.Idle += idle_handler
                
        except Exception as e:
            log_message("Error handling client: {0}".format(str(e)))
            traceback.print_exc()
        finally:
            try:
                client.close()
            except:
                pass
    
    def execute_command(self, command):
        """Execute a command received from the client"""
        try:
            command_type = command.get("type")
            params = command.get("params", {})
            
            if command_type == "get_rhino_scene_info":
                return self._get_rhino_scene_info(params)
            elif command_type == "_rhino_create_cube":
                return self._create_cube(params)
            elif command_type == "get_rhino_layers":
                return self._get_rhino_layers()
            elif command_type == "execute_code":
                return self._execute_rhino_code(params)
            elif command_type == "execute_rhinoscript_python_code":
                return self._execute_rhino_code({"code": params.get("code", "")})
            elif command_type == "get_rhino_objects_with_metadata":
                return self._get_rhino_objects_with_metadata(params)
            elif command_type == "capture_rhino_viewport":
                return self._capture_rhino_viewport(params)
            elif command_type == "get_document_summary":
                return self._get_document_summary()
            elif command_type == "get_objects":
                return self._get_objects(params)
            elif command_type == "get_object_info":
                return self._get_object_info(params)
            elif command_type == "get_selected_objects_info":
                return self._get_selected_objects_info()
            elif command_type == "create_layer":
                return self._create_layer(params)
            elif command_type == "delete_layer":
                return self._delete_layer(params)
            elif command_type == "get_or_set_current_layer":
                return self._get_or_set_current_layer(params)
            elif command_type == "create_object":
                return self._create_object(params)
            elif command_type == "delete_object":
                return self._delete_object(params)
            elif command_type == "modify_object":
                return self._modify_object(params)
            elif command_type == "select_objects":
                return self._select_objects(params)
            elif command_type == "boolean_union":
                return self._boolean_union(params)
            elif command_type == "boolean_difference":
                return self._boolean_difference(params)
            elif command_type == "boolean_intersection":
                return self._boolean_intersection(params)
            elif command_type == "loft":
                return self._loft(params)
            elif command_type == "extrude_curve":
                return self._extrude_curve(params)
            elif command_type == "sweep1":
                return self._sweep1(params)
            elif command_type == "offset_curve":
                return self._offset_curve(params)
            elif command_type == "pipe":
                return self._pipe(params)
            elif command_type == "trim_curve":
                return self._trim_curve(params)
            elif command_type == "join_curves":
                return self._join_curves(params)
            elif command_type == "curve_domain":
                return self._curve_domain(params)
            elif command_type == "trim_curve_by_fraction":
                return self._trim_curve_by_fraction(params)

            elif command_type == "ring_blank":
                return self._ring_blank(params)
            elif command_type == "head_blank":
                return self._head_blank(params)
            elif command_type == "section_profile":
                return self._section_profile(params)
            elif command_type == "place_head_on_band":
                return self._place_head_on_band(params)
            elif command_type == "edge_selector_presets":
                return self._edge_selector_presets(params)
            elif command_type == "safe_boolean_union":
                return self._safe_boolean_union(params)
            elif command_type == "safe_boolean_difference":
                return self._safe_boolean_difference(params)
            elif command_type == "loft_sections":
                return self._loft_sections(params)
            elif command_type == "add_rhino_object_metadata":
                return self._add_rhino_object_metadata(
                    params.get("object_id"), 
                    params.get("name"), 
                    params.get("description")
                )
            elif command_type == "get_rhino_selected_objects":
                return self._get_rhino_selected_objects(params)
            elif command_type == "grasshopper_add_components":
                return self._grasshopper_add_components(params)
            elif command_type == "grasshopper_get_definition_info":
                return self._grasshopper_get_definition_info()
            elif command_type == "grasshopper_run_solver":
                return self._grasshopper_run_solver(params)
            elif command_type == "grasshopper_clear_canvas":
                return self._grasshopper_clear_canvas()
            elif command_type == "grasshopper_list_available_components":
                return self._grasshopper_list_available_components()
            else:
                return {"status": "error", "message": "Unknown command type"}
                
        except Exception as e:
            log_message("Error executing command: {0}".format(str(e)))
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
    
    def _get_rhino_scene_info(self, params=None):
        """Get simplified scene information focusing on layers and example objects"""
        try:
            doc = sc.doc
            if not doc:
                return {
                    "status": "error",
                    "message": "No active document"
                }
            
            log_message("Getting simplified scene info...")
            layers_info = []

            # Get unit system information
            unit_system_code = rs.UnitSystem()
            unit_system_names = {
                0: "No unit system",
                1: "Microns",
                2: "Millimeters", 
                3: "Centimeters",
                4: "Meters",
                5: "Kilometers",
                6: "Microinches",
                7: "Mils",
                8: "Inches",
                9: "Feet",
                10: "Miles",
                11: "Custom Unit System",
                12: "Angstroms",
                13: "Nanometers",
                14: "Decimeters",
                15: "Dekameters",
                16: "Hectometers",
                17: "Megameters",
                18: "Gigameters",
                19: "Yards",
                20: "Printer point",
                21: "Printer pica",
                22: "Nautical mile",
                23: "Astronomical",
                24: "Lightyears",
                25: "Parsecs"
            }
            
            unit_system_name = unit_system_names.get(unit_system_code, "Unknown")
            
            for layer in doc.Layers:
                layer_objects = [obj for obj in doc.Objects if obj.Attributes.LayerIndex == layer.Index]
                example_objects = []
                
                for obj in layer_objects[:5]:  # Limit to 5 example objects per layer
                    try:
                        # Convert NameValueCollection to dictionary
                        user_strings = {}
                        if obj.Attributes.GetUserStrings():
                            for key in obj.Attributes.GetUserStrings():
                                user_strings[key] = obj.Attributes.GetUserString(key)
                        
                        obj_info = {
                            "id": str(obj.Id),
                            "name": obj.Name or "Unnamed",
                            "type": obj.Geometry.GetType().Name if obj.Geometry else "Unknown",
                            "metadata": user_strings  # Now using the converted dictionary
                        }
                        example_objects.append(obj_info)
                    except Exception as e:
                        log_message("Error processing object: {0}".format(str(e)))
                        continue
                
                layer_info = {
                    "full_path": layer.FullPath,
                    "object_count": len(layer_objects),
                    "is_visible": layer.IsVisible,
                    "is_locked": layer.IsLocked,
                    "example_objects": example_objects
                }
                layers_info.append(layer_info)
            
            response = {
                "status": "success",
                "unit_system": {
                    "code": unit_system_code,
                    "name": unit_system_name
                },
                "layers": layers_info
            }
            
            log_message("Simplified scene info collected successfully: {0}".format(json.dumps(response)))
            return response
            
        except Exception as e:
            log_message("Error getting simplified scene info: {0}".format(str(e)))
            return {
                "status": "error",
                "message": str(e),
                "layers": []
            }
    
    def _create_cube(self, params):
        """Create a cube in the scene"""
        try:
            size = float(params.get("size", 1.0))
            location = params.get("location", [0, 0, 0])
            name = params.get("name", "Cube")
            
            # Create cube using RhinoCommon
            box = Rhino.Geometry.Box(
                Rhino.Geometry.Plane.WorldXY,
                Rhino.Geometry.Interval(0, size),
                Rhino.Geometry.Interval(0, size),
                Rhino.Geometry.Interval(0, size)
            )
            
            # Move to specified location
            transform = Rhino.Geometry.Transform.Translation(
                location[0] - box.Center.X,
                location[1] - box.Center.Y,
                location[2] - box.Center.Z
            )
            box.Transform(transform)
            
            # Add to document
            id = sc.doc.Objects.AddBox(box)
            if id != System.Guid.Empty:
                obj = sc.doc.Objects.Find(id)
                if obj:
                    obj.Name = name
                    sc.doc.Views.Redraw()
                    return {
                        "status": "success",
                        "message": "Created cube with size {0}".format(size),
                        "id": str(id)
                    }
            
            return {"status": "error", "message": "Failed to create cube"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _get_rhino_layers(self):
        """Get information about all layers"""
        try:
            doc = sc.doc
            layers = []
            
            for layer in doc.Layers:
                layers.append({
                    "id": layer.Index,
                    "name": layer.Name,
                    "object_count": layer.ObjectCount,
                    "is_visible": layer.IsVisible,
                    "is_locked": layer.IsLocked
                })
            
            return {
                "status": "success",
                "layers": layers
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # -----------------------------------------------------------------
    # RhinoMCP contract-compatible commands (subset)
    # -----------------------------------------------------------------

    def _get_document_summary(self):
        try:
            doc = sc.doc
            if not doc:
                return {"status": "error", "message": "No active document"}

            unit_code = rs.UnitSystem()
            layer_count = doc.Layers.Count
            obj_count = doc.Objects.Count
            return {
                "status": "success",
                "document": {
                    "name": doc.Name,
                    "path": doc.Path,
                    "unit_system_code": unit_code,
                    "layer_count": layer_count,
                    "object_count": obj_count,
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_objects(self, params):
        try:
            filters = (params or {}).get("filters", {}) or {}
            limit = int((params or {}).get("limit", 500))

            layer = filters.get("layer")
            name = filters.get("name")
            obj_type = filters.get("type")
            selected_only = bool(filters.get("selected_only", False))
            ids = filters.get("ids")

            if ids:
                guids = [System.Guid(i) for i in ids]
                rh_objs = [sc.doc.Objects.FindId(g) for g in guids]
                rh_objs = [o for o in rh_objs if o]
            else:
                rh_objs = list(sc.doc.Objects)

            out = []
            for obj in rh_objs:
                if selected_only and not obj.IsSelected(False):
                    continue
                if layer:
                    lyr = sc.doc.Layers[obj.Attributes.LayerIndex]
                    if not lyr or lyr.FullPath != layer and lyr.Name != layer:
                        continue
                if name and obj.Name != name:
                    continue
                if obj_type:
                    tname = obj.Geometry.GetType().Name if obj.Geometry else "Unknown"
                    if tname != obj_type:
                        continue

                out.append({
                    "id": str(obj.Id),
                    "name": obj.Name or "",
                    "type": obj.Geometry.GetType().Name if obj.Geometry else "Unknown",
                    "layer": sc.doc.Layers[obj.Attributes.LayerIndex].FullPath if sc.doc.Layers[obj.Attributes.LayerIndex] else "",
                    "is_selected": bool(obj.IsSelected(False)),
                })
                if len(out) >= limit:
                    break

            return {"status": "success", "objects": out, "count": len(out)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_object_info(self, params):
        try:
            object_id = (params or {}).get("object_id")
            if not object_id:
                return {"status": "error", "message": "object_id is required"}
            obj = sc.doc.Objects.FindId(System.Guid(object_id))
            if not obj:
                return {"status": "error", "message": "Object not found"}

            lyr = sc.doc.Layers[obj.Attributes.LayerIndex]
            bbox = obj.Geometry.GetBoundingBox(True)
            user_strings = {}
            if obj.Attributes.GetUserStrings():
                for key in obj.Attributes.GetUserStrings():
                    user_strings[key] = obj.Attributes.GetUserString(key)

            return {
                "status": "success",
                "object": {
                    "id": str(obj.Id),
                    "name": obj.Name or "",
                    "type": obj.Geometry.GetType().Name if obj.Geometry else "Unknown",
                    "layer": lyr.FullPath if lyr else "",
                    "is_locked": bool(obj.IsLocked),
                    "is_visible": bool(obj.IsVisible),
                    "bbox": {
                        "min": [bbox.Min.X, bbox.Min.Y, bbox.Min.Z],
                        "max": [bbox.Max.X, bbox.Max.Y, bbox.Max.Z]
                    },
                    "user_text": user_strings
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_selected_objects_info(self):
        try:
            ids = rs.SelectedObjects(False, False)
            if not ids:
                return {"status": "success", "objects": [], "count": 0}
            objs = []
            for oid in ids:
                info = self._get_object_info({"object_id": str(oid)})
                if info.get("status") == "success":
                    objs.append(info["object"])
            return {"status": "success", "objects": objs, "count": len(objs)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _create_layer(self, params):
        try:
            layer_name = (params or {}).get("layer_name")
            parent = (params or {}).get("parent")
            color = (params or {}).get("color")
            if not layer_name:
                return {"status": "error", "message": "layer_name is required"}

            full = layer_name
            if parent:
                full = parent + "::" + layer_name

            if rs.IsLayer(full):
                return {"status": "success", "layer": full, "message": "Layer already exists"}

            idx = rs.AddLayer(full)
            if idx is None:
                return {"status": "error", "message": "Failed to create layer"}

            if color and isinstance(color, list) and len(color) >= 3:
                try:
                    rs.LayerColor(full, System.Drawing.Color.FromArgb(int(color[0]), int(color[1]), int(color[2])))
                except:
                    pass

            return {"status": "success", "layer": full}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _delete_layer(self, params):
        try:
            layer_name = (params or {}).get("layer_name")
            purge = bool((params or {}).get("purge", False))
            if not layer_name:
                return {"status": "error", "message": "layer_name is required"}
            if not rs.IsLayer(layer_name):
                return {"status": "error", "message": "Layer not found"}

            ok = rs.DeleteLayer(layer_name)
            if not ok:
                return {"status": "error", "message": "Failed to delete layer (may contain objects)"}
            if purge:
                try:
                    sc.doc.Layers.Purge()
                except:
                    pass
            return {"status": "success", "message": "Layer deleted"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_or_set_current_layer(self, params):
        try:
            layer_name = (params or {}).get("layer_name")
            if layer_name:
                if not rs.IsLayer(layer_name):
                    return {"status": "error", "message": "Layer not found"}
                rs.CurrentLayer(layer_name)
            return {"status": "success", "current_layer": rs.CurrentLayer()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _apply_attributes(self, object_id, attributes):
        if not object_id:
            return
        if not attributes:
            return
        try:
            if attributes.get("name"):
                rs.ObjectName(object_id, attributes.get("name"))
            if attributes.get("layer"):
                rs.ObjectLayer(object_id, attributes.get("layer"))
            if attributes.get("color") and isinstance(attributes.get("color"), list) and len(attributes.get("color")) >= 3:
                c = attributes.get("color")
                rs.ObjectColor(object_id, System.Drawing.Color.FromArgb(int(c[0]), int(c[1]), int(c[2])))
        except:
            pass

    def _create_object(self, params):
        try:
            object_type = (params or {}).get("object_type")
            p = (params or {}).get("params", {}) or {}
            attributes = (params or {}).get("attributes", {}) or {}
            if not object_type:
                return {"status": "error", "message": "object_type is required"}

            oid = None
            t = object_type.lower()
            if t == "point":
                xyz = p.get("point", [0, 0, 0])
                oid = rs.AddPoint(xyz)
            elif t == "line":
                a = p.get("from", [0, 0, 0])
                b = p.get("to", [1, 0, 0])
                oid = rs.AddLine(a, b)
            elif t == "polyline":
                pts = p.get("points", [])
                oid = rs.AddPolyline(pts)
            elif t == "circle":
                center = p.get("center", [0, 0, 0])
                radius = float(p.get("radius", 1.0))
                plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(center[0], center[1], center[2]), Rhino.Geometry.Vector3d.ZAxis)
                oid = rs.AddCircle(plane, radius)
            elif t == "rectangle":
                corner = p.get("corner", [0, 0, 0])
                width = float(p.get("width", 1.0))
                height = float(p.get("height", 1.0))
                oid = rs.AddRectangle(corner, width, height)
            elif t == "box":
                base = p.get("base", [0, 0, 0])
                dx = float(p.get("dx", 1.0)); dy = float(p.get("dy", 1.0)); dz = float(p.get("dz", 1.0))
                x0, y0, z0 = base
                corners = [
                    [x0, y0, z0], [x0+dx, y0, z0], [x0+dx, y0+dy, z0], [x0, y0+dy, z0],
                    [x0, y0, z0+dz], [x0+dx, y0, z0+dz], [x0+dx, y0+dy, z0+dz], [x0, y0+dy, z0+dz],
                ]
                oid = rs.AddBox(corners)
            elif t == "sphere":
                center = p.get("center", [0, 0, 0])
                radius = float(p.get("radius", 1.0))
                oid = rs.AddSphere(center, radius)
            elif t == "cylinder":
                base = p.get("base", [0, 0, 0])
                height = float(p.get("height", 1.0))
                radius = float(p.get("radius", 1.0))
                oid = rs.AddCylinder(base, height, radius, cap=True)
            else:
                return {"status": "error", "message": "Unsupported object_type: {0}".format(object_type)}

            if not oid:
                return {"status": "error", "message": "Failed to create object"}

            self._apply_attributes(oid, attributes)
            sc.doc.Views.Redraw()
            return {"status": "success", "object_id": str(oid)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _delete_object(self, params):
        try:
            object_id = (params or {}).get("object_id")
            if not object_id:
                return {"status": "error", "message": "object_id is required"}
            ok = rs.DeleteObject(System.Guid(object_id))
            sc.doc.Views.Redraw()
            return {"status": "success", "deleted": bool(ok)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _modify_object(self, params):
        try:
            object_id = (params or {}).get("object_id")
            ops = (params or {}).get("operations", {}) or {}
            if not object_id:
                return {"status": "error", "message": "object_id is required"}
            oid = System.Guid(object_id)
            if not rs.IsObject(oid):
                return {"status": "error", "message": "Object not found"}

            # transforms
            if ops.get("move"):
                v = ops.get("move")
                rs.MoveObject(oid, v)
            if ops.get("scale"):
                s = ops.get("scale")
                center = s.get("center", rs.ObjectBoundingBox(oid)[0])
                factor = float(s.get("factor", 1.0))
                rs.ScaleObject(oid, center, [factor, factor, factor])
            if ops.get("rotate"):
                r = ops.get("rotate")
                center = r.get("center", [0, 0, 0])
                angle = float(r.get("angle_degrees", 0.0))
                axis = r.get("axis", [0, 0, 1])
                rs.RotateObject(oid, center, angle, axis)

            # attributes
            self._apply_attributes(oid, ops.get("attributes", {}))
            sc.doc.Views.Redraw()
            return {"status": "success", "object_id": object_id}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _select_objects(self, params):
        try:
            filters = (params or {}).get("filters", {}) or {}
            mode = (params or {}).get("mode", "replace")

            ids = filters.get("ids")
            layer = filters.get("layer")
            name = filters.get("name")
            obj_type = filters.get("type")

            matches = []
            if ids:
                matches = [System.Guid(i) for i in ids]
            else:
                for obj in sc.doc.Objects:
                    lyr = sc.doc.Layers[obj.Attributes.LayerIndex]
                    if layer and lyr and lyr.FullPath != layer and lyr.Name != layer:
                        continue
                    if name and obj.Name != name:
                        continue
                    if obj_type:
                        tname = obj.Geometry.GetType().Name if obj.Geometry else "Unknown"
                        if tname != obj_type:
                            continue
                    matches.append(obj.Id)

            if mode == "replace":
                rs.UnselectAllObjects()
                rs.SelectObjects(matches)
            elif mode == "add":
                rs.SelectObjects(matches)
            elif mode == "subtract":
                rs.UnselectObjects(matches)
            else:
                return {"status": "error", "message": "Unknown selection mode"}

            sc.doc.Views.Redraw()
            return {"status": "success", "selected_count": len(matches), "ids": [str(i) for i in matches]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ---- geometry ----
    def _boolean_union(self, params):
        try:
            ids = (params or {}).get("object_ids") or []
            gids = [System.Guid(i) for i in ids]
            res = rs.BooleanUnion(gids)
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res or [])]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _boolean_difference(self, params):
        try:
            base_id = (params or {}).get("base_id")
            cutter_ids = (params or {}).get("cutter_ids") or []
            if not base_id:
                return {"status": "error", "message": "base_id is required"}
            res = rs.BooleanDifference(System.Guid(base_id), [System.Guid(i) for i in cutter_ids])
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res or [])]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _boolean_intersection(self, params):
        try:
            ids = (params or {}).get("object_ids") or []
            gids = [System.Guid(i) for i in ids]
            res = rs.BooleanIntersection(gids)
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res or [])]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _loft(self, params):
        try:
            curve_ids = (params or {}).get("curve_ids") or []
            closed = bool((params or {}).get("closed", False))
            gids = [System.Guid(i) for i in curve_ids]
            res = rs.AddLoftSrf(gids, None, None, None, closed)
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res or [])]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _extrude_curve(self, params):
        try:
            curve_id = (params or {}).get("curve_id")
            direction = (params or {}).get("direction", [0, 0, 1])
            cap = bool((params or {}).get("cap", True))
            if not curve_id:
                return {"status": "error", "message": "curve_id is required"}
            cid = System.Guid(curve_id)
            start = rs.CurveStartPoint(cid)
            end = [start.X + float(direction[0]), start.Y + float(direction[1]), start.Z + float(direction[2])]
            res = rs.ExtrudeCurveStraight(cid, [start.X, start.Y, start.Z], end)
            if cap and res:
                try:
                    rs.CapPlanarHoles(res)
                except:
                    pass
            sc.doc.Views.Redraw()
            return {"status": "success", "result_id": str(res) if res else None}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _sweep1(self, params):
        try:
            rail_id = (params or {}).get("rail_id")
            shape_ids = (params or {}).get("shape_ids") or []
            closed = bool((params or {}).get("closed", False))
            if not rail_id or not shape_ids:
                return {"status": "error", "message": "rail_id and shape_ids required"}
            res = rs.AddSweep1(System.Guid(rail_id), [System.Guid(i) for i in shape_ids], closed)
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res or [])]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _offset_curve(self, params):
        try:
            curve_id = (params or {}).get("curve_id")
            distance = float((params or {}).get("distance", 0.0))
            plane = (params or {}).get("plane", "WorldXY")
            if not curve_id:
                return {"status": "error", "message": "curve_id is required"}
            if plane == "WorldXY":
                pl = Rhino.Geometry.Plane.WorldXY
            else:
                pl = Rhino.Geometry.Plane.WorldXY
            res = rs.OffsetCurve(System.Guid(curve_id), pl, distance)
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res or [])]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _pipe(self, params):
        try:
            curve_id = (params or {}).get("curve_id")
            radius = float((params or {}).get("radius", 1.0))
            cap = (params or {}).get("cap", "round")
            if not curve_id:
                return {"status": "error", "message": "curve_id is required"}
            cap_map = {"none": 0, "flat": 1, "round": 2}
            cap_type = cap_map.get(str(cap).lower(), 2)
            res = rs.AddPipe(System.Guid(curve_id), 0, radius, cap_type=cap_type)
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res or [])]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _trim_curve(self, params):
        """Trim curve to the interval [interval_min, interval_max] (parameters to keep)."""
        try:
            p = params or {}
            curve_id = p.get("curve_id")
            interval_min = float(p.get("interval_min", p.get("interval", [0, 1])[0]))
            interval_max = float(p.get("interval_max", p.get("interval", [0, 1])[1]))
            delete_input = bool(p.get("delete_input", True))
            if not curve_id:
                return {"status": "error", "message": "curve_id is required"}
            interval = [interval_min, interval_max]
            res = rs.TrimCurve(System.Guid(curve_id), interval, delete_input)
            sc.doc.Views.Redraw()
            if res is None:
                return {"status": "error", "message": "TrimCurve failed"}
            return {"status": "success", "curve_id": str(res)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _join_curves(self, params):
        """Join two or more curves into one or more curves."""
        try:
            p = params or {}
            curve_ids = p.get("curve_ids", p.get("curves", []))
            delete_input = bool(p.get("delete_input", False))
            tolerance = p.get("tolerance")
            if not curve_ids or len(curve_ids) < 2:
                return {"status": "error", "message": "curve_ids (at least 2) is required"}
            guids = [System.Guid(cid) for cid in curve_ids]
            if tolerance is not None:
                res = rs.JoinCurves(guids, delete_input, float(tolerance))
            else:
                res = rs.JoinCurves(guids, delete_input)
            sc.doc.Views.Redraw()
            if res is None:
                return {"status": "error", "message": "JoinCurves failed"}
            try:
                ids = [str(g) for g in res]
            except TypeError:
                ids = [str(res)]
            return {"status": "success", "curve_ids": ids}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _execute_rhino_code(self, params):
        """Execute arbitrary Python code"""
        try:
            code = params.get("code", "")
            if not code:
                return {"status": "error", "message": "No code provided"}
            
            log_message("Executing code: {0}".format(code))
            
            # Create a list to store printed output
            printed_output = []
            
            # Override print function to capture output
            def custom_print(*args, **kwargs):
                output = " ".join(str(arg) for arg in args)
                printed_output.append(output)
                # Also print to Rhino's command line
                Rhino.RhinoApp.WriteLine(output)
            
            # Create execution environment with custom print in both global and local scope
            exec_globals = globals().copy()
            exec_globals['print'] = custom_print
            exec_globals['printed_output'] = printed_output
            
            local_dict = {'print': custom_print, 'printed_output': printed_output}
            
            try:
                # Execute the code with custom print in both scopes
                # To Do: Find a way to add the script running to the history
                exec(code, exec_globals, local_dict)
                
                # Get result from local_dict or use a default message
                result = local_dict.get("result", "Code executed successfully")
                log_message("Code execution completed. Result: {0}".format(result))
                
                response = {
                    "status": "success",
                    "result": str(result),
                    "printed_output": printed_output,  # Include captured print output
                    #"variables": {k: str(v)  k, v in local_dict.items() if not k.startswith('__')}
                }
                
                log_message("Sending response: {0}".format(json.dumps(response)))
                return response
                
            except Exception as e:
                # hint = "Did you use f-string formatting? You have to use IronPython here that doesn't support this."
                error_response = {
                    "status": "error",
                    "message": str(e),
                    "printed_output": printed_output  # Include any output captured before the error
                }
                log_message("Error: {0}".format(error_response))
                return error_response
                
        except Exception as e:
            # hint = "Did you use f-string formatting? You have to use IronPython here that doesn't support this."
            error_response = {
                "status": "error",
                "message": str(e),
            }
            log_message("System error: {0}".format(error_response))
            return error_response

    
# ---- jewelry helpers ----

def _get_brep_from_object_id(oid):
    """Get a Rhino.Geometry.Brep from a Rhino object id (string GUID)."""
    try:
        guid = System.Guid(str(oid))
        rh_obj = sc.doc.Objects.Find(guid)
        if rh_obj is None:
            return None
        geo = rh_obj.Geometry
        brep = geo if isinstance(geo, Rhino.Geometry.Brep) else None
        if brep is None:
            brep = Rhino.Geometry.Brep.TryConvertBrep(geo)
        return brep
    except:
        return None

def _compute_named_edge_sets(oid):
    """Compute common edge-index sets for a Brep object.
    Returns a dict of named edge index lists. Heuristic.
    """
    brep = _get_brep_from_object_id(oid)
    if brep is None:
        return None

    try:
        bbox = brep.GetBoundingBox(True)
        zmin, zmax = bbox.Min.Z, bbox.Max.Z
        zmid = (zmin + zmax) / 2.0

        rad_list = []
        top_edges = []
        bottom_edges = []

        for i, e in enumerate(brep.Edges):
            try:
                mp = e.PointAtNormalizedLength(0.5)
            except:
                mp = e.PointAt(0.5)
            r = (mp.X**2 + mp.Y**2) ** 0.5
            rad_list.append((r, i))
            if mp.Z > zmid:
                top_edges.append(i)
            if mp.Z < zmid:
                bottom_edges.append(i)

        inner_edges = []
        outer_edges = []
        if rad_list:
            rad_list.sort()
            rmin, rmax = rad_list[0][0], rad_list[-1][0]
            thr = (rmin + rmax) / 2.0
            inner_edges = [i for (r,i) in rad_list if r <= thr]
            outer_edges = [i for (r,i) in rad_list if r >= thr]

        # Primary names (LLM-friendly)
        edge_sets = {
            "band_outer_edges": outer_edges,
            "band_inner_edges": inner_edges,
            "top_perimeter_edges": top_edges,
            "bottom_perimeter_edges": bottom_edges,
        }
        # Backward-compatible aliases
        edge_sets["outer_band_edges"] = outer_edges
        edge_sets["inner_band_edges"] = inner_edges

        # Head-specific convenience alias (for extruded heads, base is bottom)
        edge_sets["head_perimeter_edges"] = bottom_edges

        return edge_sets
    except:
        return None

def _ring_blank(self, params):
    """Create a simple ring blank solid using robust cylinder booleans.
    Params:
      inner_diameter_mm (float) OR inner_radius_mm (float)
      band_width_mm (float)  -> along Z
      band_thickness_mm (float) -> radial thickness
      profile (str): flat|comfort|halfround (currently flat/comfort supported)
      center (list[3]) optional (defaults [0,0,0])
    Returns: {"status":"success","ring_id":<guid>,"cutters":[...], "computed":{...}, "warnings":[...]}
    """
    warnings = []
    try:
        p = params or {}
        center = p.get("center", [0.0, 0.0, 0.0])
        band_width = float(p.get("band_width_mm", 0.0))
        band_thickness = float(p.get("band_thickness_mm", 0.0))
        inner_diam = p.get("inner_diameter_mm", None)
        inner_rad = p.get("inner_radius_mm", None)

        if inner_diam is None and inner_rad is None:
            return {"status": "error", "message": "inner_diameter_mm or inner_radius_mm is required"}
        if band_width <= 0 or band_thickness <= 0:
            return {"status": "error", "message": "band_width_mm and band_thickness_mm must be > 0"}

        if inner_rad is None:
            inner_rad = float(inner_diam) / 2.0
        else:
            inner_rad = float(inner_rad)
            inner_diam = inner_rad * 2.0

        outer_rad = inner_rad + band_thickness

        # Build cylinders along Z, centered at center.z
        z0 = float(center[2]) - (band_width / 2.0)
        base = [float(center[0]), float(center[1]), z0]

        outer = rs.AddCylinder(base, band_width, outer_rad, cap=True)
        inner = rs.AddCylinder(base, band_width, inner_rad, cap=True)
        if not outer or not inner:
            if outer: rs.DeleteObject(outer)
            if inner: rs.DeleteObject(inner)
            return {"status": "error", "message": "Failed to create ring cylinder primitives"}

        diff = rs.BooleanDifference(outer, inner)
        # rs.BooleanDifference can return list
        ring_id = None
        if isinstance(diff, list) and diff:
            ring_id = diff[0]
        else:
            ring_id = diff

        # cleanup cutters
        try:
            rs.DeleteObject(inner)
        except:
            pass
        # outer is consumed by boolean; delete if still present
        try:
            if rs.IsObject(outer):
                rs.DeleteObject(outer)
        except:
            pass

        if not ring_id:
            warnings.append("BooleanDifference failed; ring blank not created.")
            return {"status": "error", "message": "BooleanDifference failed creating ring blank", "warnings": warnings}

        # Optional: crude comfort fit by filleting interior top/bottom edges (best-effort)
        profile = (p.get("profile") or "flat").lower()
        if profile == "comfort":
            # best-effort fillet interior edges
            try:
                preset = self._edge_selector_presets({"object_id": str(ring_id), "preset": "inner_band_edges"} )
                edge_indices = preset.get("edge_indices") if preset.get("status")=="success" else []
                if edge_indices:
                    # Use RhinoCommon fillet via rs command? RhinoScriptSyntax has AddEdgeFillet maybe in Rhino 7? Use command fallback.
                    # We'll try rs.AddEdgeFillet if available.
                    rad = float(p.get("comfort_radius_mm", min(0.6, band_thickness*0.35)))
                    if hasattr(rs, "AddEdgeFillet"):
                        rs.AddEdgeFillet(ring_id, edge_indices, rad)
                    else:
                        warnings.append("Comfort fit requested but AddEdgeFillet unavailable; skipped.")
                else:
                    warnings.append("Comfort fit requested but inner edges not found; skipped.")
            except Exception as e:
                warnings.append("Comfort fit attempt failed: {0}".format(str(e)))

        sc.doc.Views.Redraw()
        return {
            "status": "success",
            "ring_id": str(ring_id),
            "edge_sets": _compute_named_edge_sets(str(ring_id)) or {},
            "computed": {
                "inner_diameter_mm": float(inner_diam),
                "inner_radius_mm": float(inner_rad),
                "outer_radius_mm": float(outer_rad),
                "band_width_mm": float(band_width),
                "band_thickness_mm": float(band_thickness),
            },
            "warnings": warnings,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "warnings": warnings}

def _head_blank(self, params):
    """Create a head blank solid (extruded from a planar curve).
    Params:
      shape: oval|rectangle|round|cushion
      length_mm, width_mm, height_mm
      center (list[3]) optional; base plane is WorldXY at center, height extrudes +Z
      corner_radius_mm (for rectangle/cushion) optional
    """
    try:
        p = params or {}
        shape = (p.get("shape") or p.get("top_shape") or "oval").lower()
        L = float(p.get("length_mm", p.get("top_length_mm", 10.0)))
        W = float(p.get("width_mm", p.get("top_width_mm", 8.0)))
        H = float(p.get("height_mm", p.get("top_height_mm", 4.0)))
        center = p.get("center", [0.0, 0.0, 0.0])
        cx, cy, cz = float(center[0]), float(center[1]), float(center[2])

        if L <= 0 or W <= 0 or H <= 0:
            return {"status": "error", "message": "length_mm, width_mm, height_mm must be > 0"}

        curve_id = None
        if shape in ("oval", "ellipse"):
            plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(cx, cy, cz), Rhino.Geometry.Vector3d.ZAxis)
            curve_id = rs.AddEllipse(plane, L/2.0, W/2.0)
        elif shape in ("round", "circle"):
            plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(cx, cy, cz), Rhino.Geometry.Vector3d.ZAxis)
            curve_id = rs.AddCircle(plane, L/2.0)
        elif shape in ("rectangle", "rect"):
            # rs.AddRectangle takes corner + width + height (in XY)
            corner = [cx - L/2.0, cy - W/2.0, cz]
            curve_id = rs.AddRectangle(corner, L, W)
            cr = float(p.get("corner_radius_mm", 0.0) or 0.0)
            if cr > 0 and hasattr(rs, "AddFilletCorners"):
                try:
                    curve_id = rs.AddFilletCorners(curve_id, cr)
                except:
                    pass
        elif shape in ("cushion",):
            corner = [cx - L/2.0, cy - W/2.0, cz]
            curve_id = rs.AddRectangle(corner, L, W)
            cr = float(p.get("corner_radius_mm", min(L, W)*0.18))
            if hasattr(rs, "AddFilletCorners"):
                try:
                    curve_id = rs.AddFilletCorners(curve_id, cr)
                except:
                    pass
        else:
            return {"status": "error", "message": "Unsupported head shape: {0}".format(shape)}

        if not curve_id:
            return {"status": "error", "message": "Failed to create head base curve"}

        solid = rs.ExtrudeCurveStraight(curve_id, [cx, cy, cz], [cx, cy, cz + H])
        if not solid:
            # try planar + extrude
            srf = rs.AddPlanarSrf(curve_id)
            if srf:
                solid = rs.ExtrudeSurface(srf, [0,0,H], cap=True)

        if not solid:
            return {"status": "error", "message": "Failed to extrude head blank"}

        # cleanup curve
        try:
            rs.DeleteObject(curve_id)
        except:
            pass

        sc.doc.Views.Redraw()
        return {"status": "success", "head_id": str(solid), "edge_sets": _compute_named_edge_sets(str(solid)) or {}}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _section_profile(self, params):
    """Create a standardized section profile curve for lofting shoulders/bridges.
    This is a helper so small LLMs don't improvise curve construction.

    Params:
      center: [x,y,z] (required)
      width_mm: float (size along X in local plane)
      height_mm: float (size along Z in local plane)
      plane: "XZ"|"XY"|"YZ" (default "XZ")  # XZ is typical for sections along Y
      shape: "rect"|"rounded_rect"|"ellipse" (default "rounded_rect")
      corner_radius_mm: float optional (for rounded_rect)
    Returns: {"status":"success","curve_id":<guid>, "warnings":[...]}
    """
    warnings = []
    try:
        p = params or {}
        c = p.get("center")
        if not c or len(c) != 3:
            return {"status":"error","message":"center [x,y,z] is required"}
        w = float(p.get("width_mm", 0.0))
        h = float(p.get("height_mm", 0.0))
        if w <= 0 or h <= 0:
            return {"status":"error","message":"width_mm and height_mm must be > 0"}
        plane_name = (p.get("plane") or "XZ").upper()
        shape = (p.get("shape") or "ROUNDED_RECT").lower()
        corner_r = p.get("corner_radius_mm", None)
        if corner_r is not None:
            corner_r = float(corner_r)
            # clamp
            corner_r = max(0.0, min(corner_r, min(w, h) * 0.49))

        # Build plane
        if plane_name == "XY":
            pl = rs.PlaneFromFrame(c, [1,0,0], [0,1,0])
            u = [1,0,0]; v = [0,1,0]
        elif plane_name == "YZ":
            pl = rs.PlaneFromFrame(c, [0,1,0], [0,0,1])
            u = [0,1,0]; v = [0,0,1]
        else:  # XZ
            pl = rs.PlaneFromFrame(c, [1,0,0], [0,0,1])
            u = [1,0,0]; v = [0,0,1]

        if shape == "ellipse":
            rx = w/2.0
            ry = h/2.0
            # rs.AddEllipse requires plane + radii
            crv = rs.AddEllipse(pl, rx, ry)
            if not crv:
                return {"status":"error","message":"Failed to create ellipse section curve"}
            return {"status":"success","curve_id":str(crv), "warnings":warnings}

        # rectangle / rounded rectangle
        # Compute 4 corners in plane: +/-u*(w/2) +/-v*(h/2)
        hw = w/2.0; hh = h/2.0
        def add_vec(a,b,scale=1.0):
            return [a[0]+b[0]*scale, a[1]+b[1]*scale, a[2]+b[2]*scale]
        # center point as list floats
        cc = [float(c[0]), float(c[1]), float(c[2])]
        p1 = add_vec(add_vec(cc,u, hw), v, hh)
        p2 = add_vec(add_vec(cc,u,-hw), v, hh)
        p3 = add_vec(add_vec(cc,u,-hw), v,-hh)
        p4 = add_vec(add_vec(cc,u, hw), v,-hh)
        poly = rs.AddPolyline([p1,p2,p3,p4,p1])
        if not poly:
            return {"status":"error","message":"Failed to create rectangle polyline"}
        crv = poly

        if shape == "rounded_rect" and corner_r and corner_r > 0:
            if hasattr(rs, "FilletCorners"):
                try:
                    fil = rs.FilletCorners(crv, corner_r)
                    if fil:
                        try:
                            rs.DeleteObject(crv)
                        except:
                            pass
                        crv = fil
                    else:
                        warnings.append("FilletCorners returned nothing; using sharp rectangle.")
                except Exception as e:
                    warnings.append("FilletCorners failed: {0}".format(str(e)))
            else:
                warnings.append("FilletCorners not available; using sharp rectangle.")

        return {"status":"success","curve_id":str(crv), "warnings":warnings}
    except Exception as e:
        return {"status":"error","message":str(e), "warnings":warnings}


def _place_head_on_band(self, params):
    """Position a head blank relative to a ring blank using bounding-box heuristics.

    Why this exists:
      Local models struggle to 'eyeball' transforms. This gives a deterministic placement.

    Params:
      ring_id: guid (required)
      head_id: guid (required)
      side: "+Y" | "-Y" | "+X" | "-X" (default "+Y")
      offset_mm: float (gap away from band outer surface, default 0.0)
      embed_mm: float (sink head into band top for union, default 0.2)
      align_x: bool (default true)
      align_z: "top"|"center" (default "top")
    Returns:
      {"status":"success","moved":true,"move_vector":[dx,dy,dz],"ring_bbox":..., "head_bbox":...}
    """
    try:
        p = params or {}
        ring_id = p.get("ring_id")
        head_id = p.get("head_id")
        if not ring_id or not head_id:
            return {"status":"error","message":"ring_id and head_id are required"}
        side = (p.get("side") or "+Y").upper()
        offset = float(p.get("offset_mm", 0.0))
        embed = float(p.get("embed_mm", 0.2))
        align_x = bool(p.get("align_x", True))
        align_z = (p.get("align_z") or "top").lower()

        rb = rs.BoundingBox(ring_id)
        hb = rs.BoundingBox(head_id)
        if not rb or not hb:
            return {"status":"error","message":"Failed to get bounding boxes for ring/head"}

        # bbox corners list[Point3d]; compute min/max
        def bbox_minmax(bb):
            xs=[pt.X for pt in bb]; ys=[pt.Y for pt in bb]; zs=[pt.Z for pt in bb]
            return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
        rminx,rmaxx,rminy,rmaxy,rminz,rmaxz = bbox_minmax(rb)
        hminx,hmaxx,hminy,hmaxy,hminz,hmaxz = bbox_minmax(hb)

        rcx = (rminx+rmaxx)/2.0
        rcy = (rminy+rmaxy)/2.0
        rcz = (rminz+rmaxz)/2.0

        hcx = (hminx+hmaxx)/2.0
        hcy = (hminy+hmaxy)/2.0
        hcz = (hminz+hmaxz)/2.0

        # Estimate outer radius in XY by bbox extents
        outer_rx = max(abs(rmaxx-rcx), abs(rminx-rcx))
        outer_ry = max(abs(rmaxy-rcy), abs(rminy-rcy))
        outer_r = max(outer_rx, outer_ry)

        head_half_x = (hmaxx-hminx)/2.0
        head_half_y = (hmaxy-hminy)/2.0
        head_half_z = (hmaxz-hminz)/2.0

        # Target head center position
        tx, ty, tz = hcx, hcy, hcz

        if align_x:
            tx = rcx

        # Place on specified side
        if side == "+X":
            ty = rcy
            tx = rcx + outer_r + head_half_x + offset
        elif side == "-X":
            ty = rcy
            tx = rcx - (outer_r + head_half_x + offset)
        elif side == "-Y":
            tx = rcx
            ty = rcy - (outer_r + head_half_y + offset)
        else:  # +Y
            tx = rcx
            ty = rcy + outer_r + head_half_y + offset

        # Z alignment: place bottom of head at ring top minus embed
        ring_top_z = rmaxz
        if align_z == "center":
            tz = rcz
        else:
            bottom_target = ring_top_z - embed
            tz = bottom_target + head_half_z

        dx = tx - hcx
        dy = ty - hcy
        dz = tz - hcz

        moved = rs.MoveObject(head_id, [dx,dy,dz])
        sc.doc.Views.Redraw()
        return {
            "status":"success",
            "moved": bool(moved),
            "move_vector":[float(dx),float(dy),float(dz)],
            "ring_bbox": {"min":[rminx,rminy,rminz],"max":[rmaxx,rmaxy,rmaxz]},
            "head_bbox": {"min":[hminx,hminy,hminz],"max":[hmaxx,hmaxy,hmaxz]},
            "computed": {"outer_radius_est_mm": float(outer_r), "ring_top_z": float(ring_top_z)}
        }
    except Exception as e:
        return {"status":"error","message":str(e)}

def _edge_selector_presets(self, params):
    """Return edge indices for common presets.
    Params:
      object_id (guid str)
      preset: outer_band_edges | inner_band_edges | top_perimeter_edges | bottom_perimeter_edges
    Returns:
      {"status":"success","edge_indices":[...],"preset":...}
    Notes:
      This is heuristic; intended to help LLM pick edges without guessing.
    """
    try:
        p = params or {}
        oid = p.get("object_id")
        preset = (p.get("preset") or "").lower()
        if not oid:
            return {"status": "error", "message": "object_id is required"}
        if not preset:
            return {"status": "error", "message": "preset is required"}

        guid = System.Guid(oid)
        rh_obj = sc.doc.Objects.Find(guid)
        if rh_obj is None:
            return {"status": "error", "message": "Object not found"}

        geo = rh_obj.Geometry
        brep = geo if isinstance(geo, Rhino.Geometry.Brep) else None
        if brep is None:
            brep = Rhino.Geometry.Brep.TryConvertBrep(geo)
        if brep is None:
            return {"status": "error", "message": "Object is not a Brep"}

        # Basic size stats
        bbox = brep.GetBoundingBox(True)
        zmin, zmax = bbox.Min.Z, bbox.Max.Z
        zmid = (zmin + zmax) / 2.0

        edge_indices = []
        for i, e in enumerate(brep.Edges):
            mp = e.PointAtNormalizedLength(0.5)
            r = (mp.X**2 + mp.Y**2) ** 0.5

            if preset == "top_perimeter_edges":
                if mp.Z > zmid:
                    edge_indices.append(i)
            elif preset == "bottom_perimeter_edges":
                if mp.Z < zmid:
                    edge_indices.append(i)
            elif preset in ("outer_band_edges", "inner_band_edges"):
                # classify by radius relative to others
                # gather later
                edge_indices.append(i)
            else:
                return {"status": "error", "message": "Unknown preset: {0}".format(preset)}

        if preset in ("outer_band_edges", "inner_band_edges"):
            # refine by radius
            rad_list = []
            for i in edge_indices:
                mp = brep.Edges[i].PointAtNormalizedLength(0.5)
                r = (mp.X**2 + mp.Y**2) ** 0.5
                rad_list.append((r, i))
            if not rad_list:
                return {"status": "success", "edge_indices": [], "preset": preset}
            rad_list.sort()
            # inner = lower half, outer = upper half (threshold mid radius)
            rmin, rmax = rad_list[0][0], rad_list[-1][0]
            thr = (rmin + rmax) / 2.0
            if preset == "inner_band_edges":
                edge_indices = [i for (r,i) in rad_list if r <= thr]
            else:
                edge_indices = [i for (r,i) in rad_list if r >= thr]

        return {"status": "success", "edge_indices": edge_indices, "preset": preset}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _safe_boolean_union(self, params):
    """Best-effort boolean union with pairwise fallback.
    Params: object_ids: [guid str]
    Returns: {"status":"success","result_id":guid,"result_ids":[...],"warnings":[...]}
    """
    warnings = []
    try:
        ids = (params or {}).get("object_ids") or []
        if len(ids) < 2:
            return {"status": "error", "message": "object_ids must contain at least 2 ids"}
        gids = [System.Guid(i) for i in ids]

        res = rs.BooleanUnion(gids)
        if res:
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in res], "warnings": warnings}

        warnings.append("BooleanUnion failed; trying pairwise union fallback.")
        current = gids[0]
        for nxt in gids[1:]:
            step = rs.BooleanUnion([current, nxt])
            if step and isinstance(step, list) and step:
                current = step[0]
            else:
                return {"status": "error", "message": "Pairwise BooleanUnion failed", "warnings": warnings}
        sc.doc.Views.Redraw()
        return {"status": "success", "result_ids": [str(current)], "warnings": warnings}
    except Exception as e:
        return {"status": "error", "message": str(e), "warnings": warnings}

def _safe_boolean_difference(self, params):
    """Best-effort boolean difference with sequential fallback.
    Params:
      base_id: guid str
      cutter_ids: [guid str]
    """
    warnings = []
    try:
        base_id = (params or {}).get("base_id")
        cutter_ids = (params or {}).get("cutter_ids") or (params or {}).get("tool_ids") or []
        if not base_id or not cutter_ids:
            return {"status": "error", "message": "base_id and cutter_ids are required"}

        base = System.Guid(base_id)
        cutters = [System.Guid(i) for i in cutter_ids]
        res = rs.BooleanDifference(base, cutters)
        if res:
            sc.doc.Views.Redraw()
            return {"status": "success", "result_ids": [str(i) for i in (res if isinstance(res, list) else [res])], "warnings": warnings}

        warnings.append("BooleanDifference failed; trying sequential subtraction.")
        current = base
        for c in cutters:
            step = rs.BooleanDifference(current, c)
            if step:
                if isinstance(step, list):
                    current = step[0]
                else:
                    current = step
            else:
                return {"status": "error", "message": "Sequential BooleanDifference failed", "warnings": warnings}
        sc.doc.Views.Redraw()
        return {"status": "success", "result_ids": [str(current)], "warnings": warnings}
    except Exception as e:
        return {"status": "error", "message": str(e), "warnings": warnings}

def _loft_sections(self, params):
    """Loft between section curves; optionally cap to a solid if planar ends exist.
    Params:
      curve_ids: [guid str]
      closed: bool (default False)
      cap: bool (default False)
    """
    try:
        ids = (params or {}).get("curve_ids") or []
        if len(ids) < 2:
            return {"status": "error", "message": "curve_ids must contain at least 2 curves"}
        curves = [System.Guid(i) for i in ids]
        loft = rs.AddLoftSrf(curves)
        if not loft:
            return {"status": "error", "message": "Loft failed"}
        result_ids = [str(i) for i in (loft if isinstance(loft, list) else [loft])]

        if (params or {}).get("cap", False):
            # attempt to join loft pieces and cap planar holes
            try:
                joined = rs.JoinSurfaces(loft, delete_input=True)
                if joined:
                    capped = rs.CapPlanarHoles(joined)
                    if capped:
                        result_ids = [str(capped)]
            except:
                pass

        sc.doc.Views.Redraw()
        return {"status": "success", "result_ids": result_ids}
    except Exception as e:
        return {"status": "error", "message": str(e)}
def _add_rhino_object_metadata(self, obj_id, name=None, description=None):
        """Add standardized metadata to an object"""
        try:
            import json
            import time
            from datetime import datetime
            
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
                # Auto-generate name if none provided
                auto_name = "{0}_{1}".format(obj_type, short_id)
                rs.ObjectName(obj_id, auto_name)
                metadata["name"] = auto_name
                
            if description:
                metadata["description"] = description
                
            # Store metadata as user text (convert bbox to string for storage)
            user_text_data = metadata.copy()
            user_text_data["bbox"] = json.dumps(bbox_data)
            
            # Add all metadata as user text
            for key, value in user_text_data.items():
                rs.SetUserText(obj_id, key, str(value))
                
            return {"status": "success"}
        except Exception as e:
            log_message("Error adding metadata: " + str(e))
            return {"status": "error", "message": str(e)}

    def _get_rhino_objects_with_metadata(self, params):
        """Get objects with their metadata, with optional filtering"""
        try:
            import re
            import json
            
            filters = params.get("filters", {})
            metadata_fields = params.get("metadata_fields")
            layer_filter = filters.get("layer")
            name_filter = filters.get("name")
            id_filter = filters.get("short_id")
            
            # Validate metadata fields
            all_fields = VALID_METADATA_FIELDS['required'] + VALID_METADATA_FIELDS['optional']
            if metadata_fields:
                invalid_fields = [f for f in metadata_fields if f not in all_fields]
                if invalid_fields:
                    return {
                        "status": "error",
                        "message": "Invalid metadata fields: " + ", ".join(invalid_fields),
                        "available_fields": all_fields
                    }
            
            objects = []
            
            for obj in sc.doc.Objects:
                obj_id = obj.Id
                
                # Apply filters
                if layer_filter:
                    layer = rs.ObjectLayer(obj_id)
                    pattern = "^" + layer_filter.replace("*", ".*") + "$"
                    if not re.match(pattern, layer, re.IGNORECASE):
                        continue
                    
                if name_filter:
                    name = obj.Name or ""
                    pattern = "^" + name_filter.replace("*", ".*") + "$"
                    if not re.match(pattern, name, re.IGNORECASE):
                        continue
                    
                if id_filter:
                    short_id = rs.GetUserText(obj_id, "short_id") or ""
                    if short_id != id_filter:
                        continue
                    
                # Build base object data with required fields
                obj_data = {
                    "id": str(obj_id),
                    "name": obj.Name or "Unnamed",
                    "type": obj.Geometry.GetType().Name,
                    "layer": rs.ObjectLayer(obj_id)
                }
                
                # Get user text data and parse stored values
                stored_data = {}
                for key in rs.GetUserText(obj_id):
                    value = rs.GetUserText(obj_id, key)
                    if key == "bbox":
                        try:
                            value = json.loads(value)
                        except:
                            value = []
                    elif key == "created_at":
                        try:
                            value = float(value)
                        except:
                            value = 0
                    stored_data[key] = value
                
                # Build metadata based on requested fields
                if metadata_fields:
                    metadata = {k: stored_data[k] for k in metadata_fields if k in stored_data}
                else:
                    metadata = {k: v for k, v in stored_data.items() 
                              if k not in VALID_METADATA_FIELDS['required']}
                
                # Only include user_text if specifically requested
                if not metadata_fields or 'user_text' in metadata_fields:
                    user_text = {k: v for k, v in stored_data.items() 
                               if k not in metadata}
                    if user_text:
                        obj_data["user_text"] = user_text
                
                # Add metadata if we have any
                if metadata:
                    obj_data["metadata"] = metadata
                    
                objects.append(obj_data)
            
            return {
                "status": "success",
                "count": len(objects),
                "objects": objects,
                "available_fields": all_fields
            }
            
        except Exception as e:
            log_message("Error filtering objects: " + str(e))
            return {
                "status": "error",
                "message": str(e),
                "available_fields": all_fields
            }

    def _capture_rhino_viewport(self, params):
        """Capture viewport with optional annotations and layer filtering"""
        try:
            layer_name = params.get("layer")
            show_annotations = params.get("show_annotations", True)
            max_size = params.get("max_size", 800)  # Default max dimension
            original_layer = rs.CurrentLayer()
            temp_dots = []

            if show_annotations:
                # Ensure annotation layer exists and is current
                if not rs.IsLayer(ANNOTATION_LAYER):
                    rs.AddLayer(ANNOTATION_LAYER, color=(255, 0, 0))
                rs.CurrentLayer(ANNOTATION_LAYER)
                
                # Create temporary text dots for each object
                for obj in sc.doc.Objects:
                    if layer_name and rs.ObjectLayer(obj.Id) != layer_name:
                        continue
                        
                    bbox = rs.BoundingBox(obj.Id)
                    if bbox:
                        pt = bbox[1]  # Use top corner of bounding box
                        short_id = rs.GetUserText(obj.Id, "short_id")
                        if not short_id:
                            short_id = datetime.now().strftime("%d%H%M%S")
                            rs.SetUserText(obj.Id, "short_id", short_id)
                        
                        name = rs.ObjectName(obj.Id) or "Unnamed"
                        text = "{0}\n{1}".format(name, short_id)
                        
                        dot_id = rs.AddTextDot(text, pt)
                        rs.TextDotHeight(dot_id, 8)
                        temp_dots.append(dot_id)
            
            try:
                view = sc.doc.Views.ActiveView
                memory_stream = MemoryStream()
                
                # Capture to bitmap
                bitmap = view.CaptureToBitmap()
                
                # Calculate new dimensions while maintaining aspect ratio
                width, height = bitmap.Width, bitmap.Height
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                
                # Create resized bitmap
                resized_bitmap = Bitmap(bitmap, new_width, new_height)
                
                # Save as JPEG (IronPython doesn't support quality parameter)
                resized_bitmap.Save(memory_stream, ImageFormat.Jpeg)
                
                bytes_array = memory_stream.ToArray()
                image_data = base64.b64encode(bytes(bytearray(bytes_array))).decode('utf-8')
                
                # Clean up
                bitmap.Dispose()
                resized_bitmap.Dispose()
                memory_stream.Dispose()
                
            finally:
                if temp_dots:
                    rs.DeleteObjects(temp_dots)
                rs.CurrentLayer(original_layer)
            
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_data
                }
            }
            
        except Exception as e:
            log_message("Error capturing viewport: " + str(e))
            if 'original_layer' in locals():
                rs.CurrentLayer(original_layer)
            return {
                "type": "text",
                "text": "Error capturing viewport: " + str(e)
            }

    def _get_rhino_selected_objects(self, params):
        """Get objects that are currently selected in Rhino, including subobjects"""
        try:            
            include_lights = params.get("include_lights", False)
            include_grips = params.get("include_grips", False)
            include_subobjects = params.get("include_subobjects", True)

            selected_objects = []
            
            # Handle subobject selections if enabled
            if include_subobjects:
                object_count = sc.doc.Objects.Count

                log_message("Checking {0} objects for both sub-objects and full-objects selection...".format(object_count))

                # Create GetObject for interactive selection
                go = Rhino.Input.Custom.GetObject()
                go.SetCommandPrompt("Select objects or subobjects (Enter when done)")
                go.SubObjectSelect = True  # Enable subobject selection
                go.DeselectAllBeforePostSelect = False
                go.EnableBottomObjectPreference = True  # Prefer edges over surfaces
                
                # Allow multiple selection
                result = go.GetMultiple(0, 0)  # min=0, max=0 means any number
                
                if result == Rhino.Input.GetResult.Object:
                    object_count = go.ObjectCount
                    if not object_count:
                        log_message("No objects selected")
                        return {
                            "status": "error",
                            "message": "No objects selected"
                        }
                    for i in range(object_count):
                        objref = go.Object(i)
                        obj = objref.Object()
                        
                        # Check if this is a subobject selection
                        component_index = objref.GeometryComponentIndex
                        
                        if component_index.ComponentIndexType != Rhino.Geometry.ComponentIndexType.InvalidType:
                            # This is a subobject selection
                            obj_id = obj.Id
                            
                            # Check if we already have this object in our list
                            existing_obj = None
                            for existing in selected_objects:
                                if existing["id"] == str(obj_id) and existing["selection_type"] == "subobject":
                                    existing_obj = existing
                                    break
                            
                            if existing_obj:
                                # Add to existing subobject list
                                existing_obj["subobjects"].append({
                                    "index": component_index.Index,
                                    "type": str(component_index.ComponentIndexType)
                                })
                            else:
                                # Create new entry
                                obj_data = {
                                    "id": str(obj_id),
                                    "name": obj.Name or "Unnamed",
                                    "type": obj.Geometry.GetType().Name if obj.Geometry else "Unknown",
                                    "layer": rs.ObjectLayer(obj_id),
                                    "selection_type": "subobject",
                                    "subobjects": [{
                                        "index": component_index.Index,
                                        "type": str(component_index.ComponentIndexType)
                                    }]
                                }
                                
                                # Get metadata
                                user_strings = {}
                                for key in rs.GetUserText(obj_id):
                                    user_strings[key] = rs.GetUserText(obj_id, key)
                                
                                if user_strings:
                                    obj_data["metadata"] = user_strings
                                    
                                selected_objects.append(obj_data)
                        else:
                            # This is a full object selection
                            obj_data = {
                                "id": str(obj.Id),
                                "name": obj.Name or "Unnamed",
                                "type": obj.Geometry.GetType().Name if obj.Geometry else "Unknown",
                                "layer": rs.ObjectLayer(obj.Id),
                                "selection_type": "full"
                            }
                            
                            # Get metadata
                            user_strings = {}
                            for key in rs.GetUserText(obj.Id):
                                user_strings[key] = rs.GetUserText(obj.Id, key)
                            
                            if user_strings:
                                obj_data["metadata"] = user_strings
                                
                            selected_objects.append(obj_data)
                
                go.Dispose()
            
            return {
                "status": "success",
                "count": len(selected_objects),
                "objects": selected_objects,
            }
            
        except Exception as e:
            log_message("Error getting selected objects: " + str(e))
            return {"status": "error", "message": str(e)}

    def _grasshopper_add_components(self, params):
        """Add components to the current Grasshopper definition"""
        try:
            components = params.get("components", [])
            if not components:
                return {"status": "error", "message": "No components specified"}
            
            # Get Grasshopper plugin
            gh = rs.GetPlugInObject('Grasshopper')
            if not gh:
                return {"status": "error", "message": "Grasshopper plugin not available"}
            
            if not gh.IsEditorLoaded():
                return {"status": "error", "message": "Grasshopper editor is not loaded"}
            
            if not Instances:
                return {"status": "error", "message": "Grasshopper Instances not available"}
            
            doc = Instances.ActiveCanvas.Document
            if not doc:
                return {"status": "error", "message": "No active Grasshopper document"}
            
            created_components = []
            component_objects = []
            
            # Create components using direct instantiation
            for i, comp_def in enumerate(components):
                comp_type = comp_def.get("type")
                position = comp_def.get("position", [100 + i * 100, 100])
                name = comp_def.get("name")
                
                try:
                    component = None
                    
                    # Create components based on type - using direct instantiation
                    if comp_type == "Number Slider" and Special:
                        component = Special.GH_NumberSlider()
                    elif comp_type == "Number" and Params:
                        component = Params.Param_Number()
                    elif comp_type == "Integer" and Params:
                        component = Params.Param_Integer()
                    elif comp_type == "Boolean" and Params:
                        component = Params.Param_Boolean()
                    elif comp_type == "Point" and Params:
                        component = Params.Param_Point()
                    elif comp_type == "Vector" and Params:
                        component = Params.Param_Vector()
                    elif comp_type == "Text" and Params:
                        component = Params.Param_String()
                    else:
                        # Try to create using Grasshopper plugin's component creation
                        gh = rs.GetPlugInObject('Grasshopper')
                        if gh and hasattr(gh, 'CreateComponent'):
                            try:
                                component = gh.CreateComponent(comp_type)
                            except:
                                pass
                    
                    if not component:
                        log_message("Unknown component type: {0}".format(comp_type))
                        continue
                    
                    # Set position
                    component.CreateAttributes()
                    if component.Attributes:
                        component.Attributes.Pivot = PointF(float(position[0]), float(position[1]))
                    
                    # Set custom name if provided
                    if name:
                        component.NickName = name
                    
                    # Add to document
                    doc.AddObject(component, False)
                    
                    created_components.append({
                        "index": i,
                        "type": comp_type,
                        "position": position,
                        "name": name or comp_type,
                        "id": str(component.InstanceGuid)
                    })
                    
                    component_objects.append(component)
                    
                except Exception as e:
                    log_message("Error creating component {0}: {1}".format(comp_type, str(e)))
                    continue
            
            # Handle connections
            for i, comp_def in enumerate(components):
                connections = comp_def.get("connections", [])
                if not connections or i >= len(component_objects):
                    continue
                    
                target_component = component_objects[i]
                
                for conn in connections:
                    try:
                        from_idx = conn.get("from_component", 0)
                        from_output = conn.get("from_output", 0)
                        to_input = conn.get("to_input", 0)
                        
                        if from_idx < len(component_objects):
                            source_component = component_objects[from_idx]
                            
                            # Connect components
                            if (hasattr(target_component, 'Params') and hasattr(source_component, 'Params') and
                                to_input < len(target_component.Params.Input) and 
                                from_output < len(source_component.Params.Output)):
                                target_component.Params.Input[to_input].AddSource(
                                    source_component.Params.Output[from_output]
                                )
                    except Exception as e:
                        log_message("Error connecting components: {0}".format(str(e)))
                        continue
            
            # Refresh canvas and run solver
            try:
                Instances.ActiveCanvas.Refresh()
                gh.RunSolver(True)
            except Exception as e:
                log_message("Error refreshing canvas or running solver: {0}".format(str(e)))
            
            return {
                "status": "success",
                "message": "Added {0} components to Grasshopper".format(len(created_components)),
                "components": created_components
            }
            
        except Exception as e:
            log_message("Error adding Grasshopper components: " + str(e))
            return {"status": "error", "message": str(e)}

    def _grasshopper_get_definition_info(self):
        """Get information about the current Grasshopper definition"""
        try:
            # Get Grasshopper plugin
            gh = rs.GetPlugInObject('Grasshopper')
            if not gh:
                return {"status": "error", "message": "Grasshopper plugin not available"}
            
            info = {
                "editor_loaded": gh.IsEditorLoaded(),
                "components": [],
                "component_count": 0
            }
            
            if gh.IsEditorLoaded() and Instances:
                
                doc = Instances.ActiveCanvas.Document
                if doc:
                    components_info = []
                    
                    for obj in doc.Objects:
                        if hasattr(obj, 'ComponentGuid'):
                            comp_info = {
                                "id": str(obj.InstanceGuid),
                                "type": obj.Name,
                                "nickname": obj.NickName,
                                "position": [obj.Attributes.Pivot.X, obj.Attributes.Pivot.Y] if obj.Attributes else [0, 0],
                                "input_count": len(obj.Params.Input) if hasattr(obj, 'Params') else 0,
                                "output_count": len(obj.Params.Output) if hasattr(obj, 'Params') else 0
                            }
                            components_info.append(comp_info)
                    
                    info["components"] = components_info
                    info["component_count"] = len(components_info)
            
            return {
                "status": "success",
                "info": info
            }
            
        except Exception as e:
            log_message("Error getting Grasshopper definition info: " + str(e))
            return {"status": "error", "message": str(e)}

    def _grasshopper_run_solver(self, params):
        """Run the Grasshopper solver"""
        try:
            force_update = params.get("force_update", True)
            
            # Get Grasshopper plugin
            gh = rs.GetPlugInObject('Grasshopper')
            if not gh:
                return {"status": "error", "message": "Grasshopper plugin not available"}
            
            if not gh.IsEditorLoaded():
                return {"status": "error", "message": "Grasshopper editor is not loaded"}
            
            # Run solver
            gh.RunSolver(force_update)
            
            return {
                "status": "success",
                "message": "Grasshopper solver executed successfully"
            }
            
        except Exception as e:
            log_message("Error running Grasshopper solver: " + str(e))
            return {"status": "error", "message": str(e)}

    def _grasshopper_clear_canvas(self):
        """Clear all components from the Grasshopper canvas"""
        try:
            # Get Grasshopper plugin
            gh = rs.GetPlugInObject('Grasshopper')
            if not gh:
                return {"status": "error", "message": "Grasshopper plugin not available"}
            
            if not gh.IsEditorLoaded():
                return {"status": "error", "message": "Grasshopper editor is not loaded"}
            
            if not Instances:
                return {"status": "error", "message": "Grasshopper Instances not available"}
            
            doc = Instances.ActiveCanvas.Document
            if doc:
                # Clear all objects
                doc.Objects.Clear()
                
                # Refresh canvas
                Instances.ActiveCanvas.Refresh()
                
                return {
                    "status": "success",
                    "message": "Grasshopper canvas cleared successfully"
                }
            else:
                return {"status": "error", "message": "No active Grasshopper document"}
            
        except Exception as e:
            log_message("Error clearing Grasshopper canvas: " + str(e))
            return {"status": "error", "message": str(e)}
    
    def _grasshopper_list_available_components(self):
        """List all available Grasshopper components for debugging"""
        try:
            # Get Grasshopper plugin
            gh = rs.GetPlugInObject('Grasshopper')
            if not gh:
                return {"status": "error", "message": "Grasshopper plugin not available"}
            
            if not gh.IsEditorLoaded():
                return {"status": "error", "message": "Grasshopper editor is not loaded"}
            
            # Return list of supported component types
            supported_components = [
                {"name": "Number Slider", "category": "Params", "subcategory": "Input"},
                {"name": "Number", "category": "Params", "subcategory": "Input"},
                {"name": "Integer", "category": "Params", "subcategory": "Input"},
                {"name": "Boolean", "category": "Params", "subcategory": "Input"},
                {"name": "Point", "category": "Params", "subcategory": "Input"},
                {"name": "Vector", "category": "Params", "subcategory": "Input"},
                {"name": "Text", "category": "Params", "subcategory": "Input"},
                {"name": "Series", "category": "Sets", "subcategory": "Sequence"},
                {"name": "Range", "category": "Sets", "subcategory": "Sequence"},
                {"name": "Cross Reference", "category": "Sets", "subcategory": "Tree"},
                {"name": "Addition", "category": "Maths", "subcategory": "Operators"},
                {"name": "Subtraction", "category": "Maths", "subcategory": "Operators"},
                {"name": "Multiplication", "category": "Maths", "subcategory": "Operators"},
                {"name": "Division", "category": "Maths", "subcategory": "Operators"},
                {"name": "Line", "category": "Curve", "subcategory": "Primitive"},
                {"name": "Circle", "category": "Curve", "subcategory": "Primitive"},
                {"name": "Rectangle", "category": "Curve", "subcategory": "Primitive"},
                {"name": "Polygon", "category": "Curve", "subcategory": "Primitive"},
                {"name": "Extrude", "category": "Surface", "subcategory": "Freeform"},
                {"name": "Move", "category": "Transform", "subcategory": "Euclidean"},
                {"name": "Rotate", "category": "Transform", "subcategory": "Euclidean"},
                {"name": "Scale", "category": "Transform", "subcategory": "Euclidean"},
                {"name": "Construct Point", "category": "Vector", "subcategory": "Point"},
            ]
            
            return {
                "status": "success",
                "components": supported_components,
                "count": len(supported_components),
                "note": "This is a list of currently supported component types. More components may be available but not yet implemented."
            }
            
        except Exception as e:
            log_message("Error listing Grasshopper components: " + str(e))
            return {"status": "error", "message": str(e)}

# Create and start server
server = RhinoMCPServer(HOST, PORT)
server.start()

# Add commands to Rhino
def start_server():
    """Start the RhinoMCP server"""
    server.start()

def stop_server():
    """Stop the RhinoMCP server"""
    server.stop()

# Automatically start the server when this script is loaded
start_server()
log_message("RhinoMCP script loaded. Server started automatically.")
log_message("To stop the server, run: stop_server()") 