import os
import subprocess
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
import threading

# 1. Start a dummy web server so Render doesn't shut us down
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    handler = SimpleHTTPRequestHandler
    # Bind to 0.0.0.0 so Render can detect it
    httpd = TCPServer(("0.0.0.0", port), handler)
    httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# 2. Start your bot
subprocess.run(["python", "bot.py"])
