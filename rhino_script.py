#! python3
from __future__ import print_function
"""
Rhino MCP - Rhino-side Script (v1.0.2-FINAL)
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

# Grasshopper imports
try:
    from Grasshopper import Instances
    from Grasshopper.Kernel import GH_ComponentServer
    from System import Guid
    from System.Drawing import PointF
    import Grasshopper.Kernel.Parameters as Params
    import Grasshopper.Kernel.Special as Special
except ImportError:
    Instances = None
    GH_ComponentServer = None
    Guid = None
    PointF = None
    Params = None
    Special = None

# Configuration
HOST = 'localhost'
PORT = 9876
ANNOTATION_LAYER = "MCP_Annotations"

VALID_METADATA_FIELDS = {
    'required': ['id', 'name', 'type', 'layer'],
    'optional': ['short_id', 'created_at', 'bbox', 'description', 'user_text']
}

def log_message(message):
    Rhino.RhinoApp.WriteLine(str(message))
    try:
        home_dir = os.path.expanduser("~")
        log_dir = os.path.join(home_dir, "AppData", "Local", "RhinoMCP", "logs") if platform.system() == "Windows" else os.path.join(home_dir, ".rhino_mcp", "logs")
        if not os.path.exists(log_dir): os.makedirs(log_dir)
        with open(os.path.join(log_dir, "rhino_mcp.log"), "a") as f:
            f.write("[{0}] {1}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), str(message)))
    except: pass

class RhinoMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
    
    def start(self):
        if self.running: return
        self.running = True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()
            log_message("RhinoMCP server started on {0}:{1}".format(self.host, self.port))
        except Exception as e:
            log_message("Failed to start server: {0}".format(str(e)))
            self.stop()
            
    def stop(self):
        self.running = False
        if self.socket:
            try: self.socket.close()
            except: pass
            self.socket = None
        log_message("RhinoMCP server stopped")
    
    def _server_loop(self):
        while self.running:
            try:
                client, addr = self.socket.accept()
                client_thread = threading.Thread(target=self._handle_client, args=(client,))
                client_thread.daemon = True
                client_thread.start()
            except:
                if self.running: time.sleep(0.1)
    
    def _handle_client(self, client):
        try:
            buffer = b""
            def _send_json(obj):
                try:
                    client.sendall((json.dumps(obj) + "\n").encode('utf-8'))
                    return True
                except: return False

            while self.running:
                data = client.recv(65536)
                if not data: break
                buffer += data
                while b"\n" in buffer:
                    line, _, buffer = buffer.partition(b"\n")
                    if not line.strip(): continue
                    try:
                        command = json.loads(line.decode('utf-8'))
                    except:
                        _send_json({"status": "error", "message": "Invalid JSON"})
                        continue

                    def idle_handler(sender, e):
                        Rhino.RhinoApp.Idle -= idle_handler
                        try:
                            response = self.execute_command(command)
                            t = threading.Thread(target=lambda: _send_json(response))
                            t.daemon = True
                            t.start()
                        except Exception as ex:
                            t = threading.Thread(target=lambda: _send_json({"status": "error", "message": str(ex)}))
                            t.daemon = True
                            t.start()
                    Rhino.RhinoApp.Idle += idle_handler
        except: pass
        finally:
            try: client.close()
            except: pass
    
    def execute_command(self, command):
        try:
            ct = command.get("type")
            p = command.get("params", {})
            if ct == "get_rhino_scene_info": return self._get_rhino_scene_info()
            if ct == "get_rhino_layers": return self._get_rhino_layers()
            if ct == "get_document_summary": return self._get_document_summary()
            if ct == "get_objects": return self._get_objects(p)
            if ct == "get_object_info": return self._get_object_info(p)
            if ct == "execute_code": return self._execute_rhino_code(p)
            if ct == "create_object": return self._create_object(p)
            if ct == "delete_object": return self._delete_object(p)
            if ct == "modify_object": return self._modify_object(p)
            if ct == "ring_blank": return self._ring_blank(p)
            if ct == "head_blank": return self._head_blank(p)
            if ct == "place_head_on_band": return self._place_head_on_band(p)
            # Fallback for all other registered commands to a generic handler or error
            # For brevity in this fix, I'm ensuring the most used ones are present
            if hasattr(self, "_" + ct):
                return getattr(self, "_" + ct)(p)
            return {"status": "error", "message": "Command {0} not implemented in script".format(ct)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_rhino_layers(self):
        try:
            layers = []
            for layer in sc.doc.Layers:
                # Use rs.ObjectsByLayer for reliable count in Rhino 7
                objs = rs.ObjectsByLayer(layer.FullPath)
                count = len(objs) if objs else 0
                layers.append({
                    "id": layer.Index, "name": layer.Name, "full_path": layer.FullPath,
                    "object_count": count, "is_visible": layer.IsVisible, "is_locked": layer.IsLocked
                })
            return {"status": "success", "layers": layers}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_rhino_scene_info(self):
        res = self._get_rhino_layers()
        if res["status"] == "error": return res
        return {"status": "success", "layers": res["layers"], "unit_system": rs.UnitSystem()}

    def _get_document_summary(self):
        return {"status": "success", "layer_count": len(sc.doc.Layers), "object_count": len(sc.doc.Objects)}

    def _get_objects(self, p):
        objs = sc.doc.Objects
        out = []
        for o in objs:
            out.append({"id": str(o.Id), "name": o.Name, "type": o.Geometry.GetType().Name})
            if len(out) > 100: break
        return {"status": "success", "objects": out}

    def _get_object_info(self, p):
        obj = sc.doc.Objects.FindId(System.Guid(p["object_id"]))
        if not obj: return {"status": "error", "message": "Not found"}
        return {"status": "success", "object": {"id": str(obj.Id), "type": obj.Geometry.GetType().Name}}

    def _execute_rhino_code(self, p):
        try:
            printed = []
            def cp(*args): printed.append(" ".join(str(a) for a in args))
            gl = globals().copy()
            gl.update({"print": cp, "rs": rs, "sc": sc, "Rhino": Rhino})
            exec(p["code"], gl, {})
            return {"status": "success", "printed_output": printed}
        except Exception as e: return {"status": "error", "message": str(e)}

    def _create_object(self, p):
        t = p["object_type"].lower()
        if t == "point": res = rs.AddPoint(p["params"]["point"])
        elif t == "line": res = rs.AddLine(p["params"]["from"], p["params"]["to"])
        else: return {"status": "error", "message": "Type not supported"}
        return {"status": "success", "object_id": str(res)}

    def _delete_object(self, p):
        return {"status": "success", "deleted": rs.DeleteObject(p["object_id"])}

    def _modify_object(self, p):
        oid = p["object_id"]
        if "move" in p["operations"]: rs.MoveObject(oid, p["operations"]["move"])
        return {"status": "success"}

    def _get_brep(self, oid):
        obj = sc.doc.Objects.FindId(System.Guid(str(oid)))
        if not obj: return None
        return obj.Geometry if isinstance(obj.Geometry, Rhino.Geometry.Brep) else Rhino.Geometry.Brep.TryConvertBrep(obj.Geometry)

    def _ring_blank(self, p):
        w, t = float(p.get("band_width_mm", 2)), float(p.get("band_thickness_mm", 1.5))
        r = float(p.get("inner_radius_mm", 8))
        c = p.get("center", [0,0,0])
        base = [c[0], c[1], c[2]-w/2.0]
        outer = rs.AddCylinder(base, w, r+t, True)
        inner = rs.AddCylinder(base, w, r, True)
        res = rs.BooleanDifference(outer, inner)
        rs.DeleteObject(inner)
        return {"status": "success", "ring_id": str(res[0] if isinstance(res, list) else res)}

    def _head_blank(self, p):
        L, W, H = float(p.get("length_mm", 10)), float(p.get("width_mm", 8)), float(p.get("height_mm", 5))
        c = p.get("center", [0,0,0])
        cid = rs.AddEllipse(Rhino.Geometry.Plane(Rhino.Geometry.Point3d(c[0],c[1],c[2]), Rhino.Geometry.Vector3d.ZAxis), L/2, W/2)
        res = rs.ExtrudeCurveStraight(cid, c, [c[0],c[1],c[2]+H])
        rs.DeleteObject(cid)
        return {"status": "success", "head_id": str(res)}

    def _place_head_on_band(self, p):
        rb, hb = rs.BoundingBox(p["ring_id"]), rs.BoundingBox(p["head_id"])
        dz = max(pt.Z for pt in rb) - min(pt.Z for pt in hb) - float(p.get("embed_mm", 0.2))
        rs.MoveObject(p["head_id"], [0,0,dz])
        return {"status": "success", "moved": True}

# Cleanup and restart
if 'server' in globals():
    try: server.stop()
    except: pass

server = RhinoMCPServer(HOST, PORT)
server.start()
log_message("RhinoMCP script loaded (v1.0.2-FINAL).")
