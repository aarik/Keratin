import rhinoscriptsyntax as rs
import scriptcontext as sc

__commandname__ = "StartKeratin"

def RunCommand(is_interactive):
    # Check if server is already running
    if "keratin_server" in sc.sticky and sc.sticky["keratin_server"] is not None:
        existing = sc.sticky["keratin_server"]
        if existing.running:
            print("Keratin server is already running on {0}:{1}".format(existing.host, existing.port))
            return 0

    # Import the server module
    import os
    import sys
    plugin_dir = os.path.dirname(__file__)
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    import rhino_script as ks

    # Create and start
    server = ks.RhinoMCPServer(ks.HOST, ks.PORT)
    server.start()

    # Stash in sticky so StopKeratin can find it
    sc.sticky["keratin_server"] = server

    print("Keratin server started on {0}:{1}".format(ks.HOST, ks.PORT))
    return 0
