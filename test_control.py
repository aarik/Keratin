import socket
import json
import time

def test_connection():
    host = 'localhost'
    port = 9876
    
    print("Connecting to Rhino at {0}:{1}...".format(host, port))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(30.0)
    try:
        s.connect((host, port))
        print("Connected!")
        
        # Test command
        command = {
            "type": "get_rhino_layers",
            "params": {}
        }
        payload = json.dumps(command) + "\n"
        print("Sending command: {0}".format(command))
        s.sendall(payload.encode('utf-8'))
        
        print("Waiting for response (30s timeout)...")
        buffer = b""
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    print("Connection closed by server")
                    break
                buffer += chunk
                if b"\n" in buffer:
                    line, _, _ = buffer.partition(b"\n")
                    response = json.loads(line.decode('utf-8'))
                    print("SUCCESS! Received response:")
                    print(json.dumps(response, indent=2))
                    return True
            except socket.timeout:
                print("STILL WAITING... (Rhino might be busy or Idle handler not firing)")
                # Continue waiting until total 30s
                continue
    except Exception as e:
        print("ERROR: {0}".format(str(e)))
    finally:
        s.close()
    return False

if __name__ == "__main__":
    test_connection()
