from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from rhino_mcp.rhino_tools import RhinoTools, RhinoConnection
from typing import Dict, Any
import logging
import json
import argparse

# configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebServer")

# create FastAPI app
app = FastAPI()

# allow cross-domain requests (restricted to localhost to prevent remote code execution)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create MCP instance and tools. All tools use get_rhino_connection() to send commands
# to the Rhino script (rhino_script.py) on localhost:9876; start Rhino and load the script first.
mcp = FastMCP("RhinoMCP")
rhino_tools = RhinoTools(mcp)

# add strategy
@mcp.prompt()
def rhino_creation_strategy() -> str:
    """Defines the preferred strategy for creating and managing objects in Rhino"""
    return """When working with Rhino through MCP, follow these guidelines:

    Especially when working with geometry, iterate with smaller steps and check the scene state from time to time.
    Act strategically with a long-term plan, think about how to organize the data and scene objects in a way that is easy to maintain and extend, by using layers and metadata (name, description),
    with the get_rhino_objects_with_metadata() function you can filter and select objects based on this metadata. You can access objects, and with the "type" attribute you can check their geometry type and
    access the geometry specific properties (such as corner points etc.) to create more complex scenes with spatial consistency. Start from sparse to detail (e.g. first the building plot, then the wall, then the window etc. - it is crucial to use metadata to be able to do that)

    1. Scene Context Awareness:
       - At the start of a session, call list_rhino_commands() for the MCP command roster and list_rhinoscript_functions() for the full Rhino 7 RhinoScriptSyntax (rs.*) API. Together these match all tools available in Rhino 7; use look_up_RhinoScriptSyntax(name) for docs and execute_rhino_code() to run any rs function.
       - Always start by checking the scene using get_rhino_scene_info() for basic overview
       - Use the capture_rhino_viewport to get an image from viewport to get a quick overview of the scene
       - Use get_rhino_objects_with_metadata() for detailed object information and filtering
       - The short_id in metadata can be displayed in viewport using capture_rhino_viewport()

    2. Object Creation and Management:
       - When creating objects, ALWAYS call add_rhino_object_metadata() after creation (The add_rhino_object_metadata() function is provided in the code context)   
       - Use meaningful names for objects to help with you with later identification, organize the scenes with layers (but not too many layers)
       - Think about grouping objects (e.g. two planes that form a window)

    3. Code Execution:
       - This is Rhino 7 with IronPython 2.7 - no f-strings or modern Python features etc
       - DONT FORGET NO f-strings! No f-strings, No f-strings!
       - Prefer automated solutions over user interaction, unless its requested or it makes sense or you struggle with errors
       - You can use rhino command syntax to ask the user questions e.g. "should i do "A" or "B"" where A,B are clickable options
       - If you got an error related to the RhinoScriptSyntax, always use the look_up_RhinoScriptSyntax tool to look up the correct syntax

    4. Best Practices:
       - Keep objects organized in appropriate layers
       - Use meaningful names and descriptions
       - Use viewport captures to verify visual results
    """


# HTTP endpoint
@app.post("/rhino/command")
async def execute_command(command: Dict[str, Any]):
    """Execute Rhino command. Body must include 'type' and optionally 'params'."""
    try:
        result = rhino_tools.execute_command(command)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error("Command execution error: {0}".format(str(e)))
        return {"status": "error", "message": str(e)}

@app.get("/rhino/scene")
async def get_scene():
    """Get scene info (no MCP context required)."""
    try:
        scene_info = rhino_tools.get_rhino_scene_info(None)
        return {"status": "success", "data": scene_info}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/rhino/strategy")
async def get_strategy():
    """get Rhino strategy"""
    return {
        "rhino_strategy": rhino_creation_strategy(),
    }

# WebSocket endpoint
# NOTE: Each WebSocket connection creates its own RhinoConnection to the Rhino listener.
# The Rhino listener (rhino_script.py) accepts multiple clients, but only one client
# should be active at a time to avoid response desynchronization.
@app.websocket("/rhino/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    rhino_conn = RhinoConnection(port=9876)

    try:
        # connect to Rhino
        rhino_conn.connect()
        logger.info("Connected to Rhino socket server")

        # send initial connection success message
        await websocket.send_json({
            "status": "connected",
            "message": "Connected to Rhino socket server"
        })

        # main message loop
        while True:
            try:
                # wait for message
                data = await websocket.receive_json()
                logger.info("Received command: {0}".format(data))

                cmd_type = data.get("type") if isinstance(data, dict) else None
                if not cmd_type:
                    await websocket.send_json({
                        "status": "error",
                        "message": "Message must be a dict with 'type'"
                    })
                    continue

                # send command to Rhino
                result = rhino_conn.send_command(cmd_type, data.get("params", {}))

                # send result
                await websocket.send_json({
                    "status": "success",
                    "data": result
                })

            except json.JSONDecodeError:
                await websocket.send_json({
                    "status": "error",
                    "message": "Invalid JSON format"
                })
            except Exception as e:
                logger.error("Command execution error: {0}".format(str(e)))
                await websocket.send_json({
                    "status": "error",
                    "message": str(e)
                })

    except Exception as e:
        logger.error("WebSocket error: {0}".format(str(e)))
        try:
            await websocket.send_json({
                "status": "error",
                "message": "Connection error: {0}".format(str(e))
            })
        except Exception:
            pass

    finally:
        # clean up connection
        try:
            rhino_conn.disconnect()
            logger.info("Disconnected from Rhino socket server")
            await websocket.close()
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="Web server port")
    parser.add_argument("--host", type=str, default="localhost", help="Web server host")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port) 