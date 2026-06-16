import rhinoscriptsyntax as rs
import scriptcontext as sc

__commandname__ = "StopKeratin"

def RunCommand(is_interactive):
    if "keratin_server" not in sc.sticky or sc.sticky["keratin_server"] is None:
        print("Keratin server is not running.")
        return 0

    server = sc.sticky["keratin_server"]
    if not server.running:
        print("Keratin server is not running.")
        sc.sticky["keratin_server"] = None
        return 0

    server.stop()
    sc.sticky["keratin_server"] = None

    print("Keratin server stopped.")
    return 0
