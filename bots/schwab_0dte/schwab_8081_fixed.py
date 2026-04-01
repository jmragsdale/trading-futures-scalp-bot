#!/usr/bin/env python3
import webbrowser
import urllib.parse
import base64
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import requests
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

print("""
╔════════════════════════════════════════╗
║   Schwab Auth - Port 8081 Fixed        ║
╚════════════════════════════════════════╝
""")

CLIENT_ID = input("Enter App Key: ").strip()
CLIENT_SECRET = input("Enter Secret: ").strip()

# IMPORTANT: Auth URL must match what's registered with Schwab
REDIRECT_URI = "https://127.0.0.1:8081"  # Your registered callback
PORT = 8081

TOKEN_RESULT = None

class InstantHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global TOKEN_RESULT
        
        if 'code=' in self.path:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            if 'code' in params:
                code = params['code'][0]
                print(f"✅ Got code! Length: {len(code)} chars")
                print(f"🔄 Exchanging immediately...")
                
                auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
                
                try:
                    response = requests.post(
                        "https://api.schwabapi.com/v1/oauth/token",
                        headers={
                            "Authorization": f"Basic {auth}",
                            "Content-Type": "application/x-www-form-urlencoded"
                        },
                        data={
                            "grant_type": "authorization_code",
                            "code": code,
                            "redirect_uri": REDIRECT_URI  # Must match exactly
                        },
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        TOKEN_RESULT = response.json()
                        
                        with open('SCHWAB_TOKENS.txt', 'w') as f:
                            f.write("# Add these to AWS Secrets Manager:\n")
                            f.write(f"refresh_token: {TOKEN_RESULT['refresh_token']}\n")
                            f.write(f"client_id: {CLIENT_ID}\n")
                            f.write(f"client_secret: {CLIENT_SECRET}\n")
                        
                        print("\n" + "="*60)
                        print("🎉 SUCCESS! GOT YOUR REFRESH TOKEN!")
                        print("="*60)
                        print("\n📋 Copy this refresh token:\n")
                        print(f"{TOKEN_RESULT['refresh_token']}")
                        print("\n✅ Full details saved to: SCHWAB_TOKENS.txt")
                        print("="*60)
                        
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b"<h1>Success! Check terminal for token.</h1>")
                        
                    else:
                        print(f"\n❌ Token exchange failed!")
                        print(f"Status: {response.status_code}")
                        print(f"Error: {response.text}")
                        
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(f"Error: {response.text}".encode())
                        
                except Exception as e:
                    print(f"\n❌ Exception: {e}")
                    self.send_response(500)
                    self.end_headers()
                
                threading.Thread(target=self.server.shutdown).start()
    
    def log_message(self, format, *args):
        pass

# Build auth URL with the registered redirect URI
auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope=api"

print(f"\n🖥️  Starting server on port {PORT}...")

# Kill anything on the port first
import os
os.system(f"lsof -ti:{PORT} | xargs kill -9 2>/dev/null")

try:
    server = HTTPServer(('127.0.0.1', PORT), InstantHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    print("✅ Server ready!")
    print(f"🌐 Opening Schwab authorization in browser...")
    print(f"   The redirect will come directly to port {PORT}")
    print("   No manual URL editing needed!\n")
    
    webbrowser.open(auth_url)
    
    print("⏳ Please:")
    print("   1. Log in to Schwab")
    print("   2. Click Authorize/Allow")
    print("   3. Wait for the success message\n")
    
    server_thread.join()
    
except OSError as e:
    print(f"\n❌ Error: Port {PORT} is in use!")
    print("Try running: lsof -ti:8081 | xargs kill -9")
    print("Then run this script again")
    
except KeyboardInterrupt:
    server.shutdown()
    print("\nCancelled")

if TOKEN_RESULT:
    print("\n✅ Done! Your refresh token is ready!")
else:
    print("\n⚠️ No token received. Please try again!")