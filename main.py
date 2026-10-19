import os
import subprocess
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
import threading

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    handler = SimpleHTTPRequestHandler
    # Binding to 0.0.0.0 is crucial
    httpd = TCPServer(("0.0.0.0", port), handler)
    httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# Run your bot
subprocess.run(["python", "bot.py"])
