"""Quick authorization code flow to get a Salesforce access token.

Opens a browser for login, captures the callback, exchanges for token.
Prints the access_token and instance_url for use in other scripts.
"""

import asyncio
import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

import httpx

CLIENT_ID = os.environ.get("SF_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET")
if not CLIENT_ID or not CLIENT_SECRET:
    print("Error: SF_CLIENT_ID and SF_CLIENT_SECRET environment variables are required.")
    print("Set them from your Salesforce Connected App settings.")
    sys.exit(1)
LOGIN_URL = os.environ.get("SF_LOGIN_URL", "https://login.salesforce.com")
REDIRECT_URI = "http://localhost:8443/callback"

auth_code_result = {}


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code_result["code"] = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Success! You can close this tab.</h2>")
        else:
            auth_code_result["error"] = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h2>Error: {auth_code_result['error']}</h2>".encode())

    def log_message(self, format, *args):
        pass  # Suppress request logging


async def main():
    # Start local callback server
    server = http.server.HTTPServer(("localhost", 8443), CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    # Open browser for authorization
    authorize_url = (
        f"{LOGIN_URL}/services/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={urllib.parse.quote(CLIENT_ID)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope=api+refresh_token"
    )

    print("Opening browser for Salesforce login...")
    print(f"If browser doesn't open, visit:\n{authorize_url}\n")
    webbrowser.open(authorize_url)

    # Wait for callback
    print("Waiting for authorization callback...")
    thread.join(timeout=120)
    server.server_close()

    if "error" in auth_code_result:
        print(f"Authorization failed: {auth_code_result['error']}")
        return

    if "code" not in auth_code_result:
        print("Timed out waiting for authorization callback.")
        return

    code = auth_code_result["code"]
    print(f"Got authorization code: {code[:20]}...")

    # Exchange code for token
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{LOGIN_URL}/services/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
        )

        if resp.status_code == 200:
            data = resp.json()
            print(f"\nAuthentication successful!")
            print(f"  Instance URL: {data['instance_url']}")
            print(f"  Access Token: {data['access_token'][:40]}...")

            # Export for use in test script
            os.environ["SF_ACCESS_TOKEN"] = data["access_token"]
            os.environ["SF_INSTANCE_URL"] = data["instance_url"]

            # Now run a quick API test
            print("\nTesting API access...")
            api_resp = await client.get(
                f"{data['instance_url']}/services/data/v62.0/sobjects/",
                headers={"Authorization": f"Bearer {data['access_token']}"},
            )
            if api_resp.status_code == 200:
                sobjects = api_resp.json()["sobjects"]
                queryable = [o for o in sobjects if o.get("queryable")]
                print(f"  Total objects: {len(sobjects)}")
                print(f"  Queryable: {len(queryable)}")
                interesting = [
                    o
                    for o in queryable
                    if o["name"] in ("Account", "Contact", "Opportunity", "Lead", "Case")
                ]
                print("  Key objects:")
                for o in interesting:
                    print(f"    - {o['name']} ({o['label']})")
                print("\nSalesforce connection verified!")
            else:
                print(f"  API call failed: {api_resp.status_code} {api_resp.text}")
        else:
            print(f"Token exchange failed: {resp.status_code}")
            print(f"  {resp.text}")


if __name__ == "__main__":
    asyncio.run(main())
