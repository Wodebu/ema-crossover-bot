import os
import subprocess
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
import threading

# 1. Start a dummy web server in the background to keep Render happy
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    handler = SimpleHTTPRequestHandler
    httpd = TCPServer(("", port), handler)
    httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# 2. Run your actual bot
subprocess.run(["python", "bot.py"])
