from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import json
import base64
import requests
import os
import hashlib
import hmac
from datetime import datetime
import time






# ========================================================================================================
# Server Configuration
# ========================================================================================================
PORT = 8000

# Billplz Sandbox credentials
BILLPLZ_API_KEY = "a09efa3d-e41e-4f9a-a756-a6ad3d2032b6"
COLLECTION_ID = "xjcqivfx"  # v3 collection ID
PAYMENT_ORDER_COLLECTION_ID = "8db85a25-d2f7-4372-8499-ccdd257dd906"  # v5 collection ID
XSIGNATURE_KEY = "9650acc45cd802f77a95dc4dc4787651e41f8fdb278fb8ddc08608b0bbe318f195d57dc0bec9bf0f6770d843b31501bf05e2a66572ed8371cbbae0a15378a23c"

# Base URL for Billplz API
BILLPLZ_BASE_URL = "https://www.billplz-sandbox.com/api"

# Your ngrok URL for callbacks
CALLBACK_BASE_URL = "https://c3365aff5c38.ngrok-free.app"

# Data storage files
DATA_FILES = {
    "bills": "bills.json",
    "payment_form": "payment_form.json",
    "payment_orders": "payment_orders.json",
    "callbacks": "callbacks.json"
}


# ========================================================================================================
# Utility Functions
# ========================================================================================================
def save_data(data_type, data):
    file_path = DATA_FILES.get(data_type, "data.json")
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            json.dump([], f)
    try:
        with open(file_path, "r") as f:
            records = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        records = []

    data["saved_at"] = datetime.now().isoformat()
    records.append(data)

    with open(file_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"💾 Saved {data_type} data to {file_path}")

def load_data(data_type):
    file_path = DATA_FILES.get(data_type, "data.json")
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

# ========================================================================================================
# HTTP Request Handler
# ========================================================================================================
class EnhancedBillplzHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default logging

# ------------------------------ Helpers ------------------------------
    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def send_html_response(self, html_content, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def make_billplz_request(self, endpoint, method="GET", data=None, version="v3"):
        """Dynamic API versioning"""
        url = f"{BILLPLZ_BASE_URL}/{version}/{endpoint}"
        auth_header = base64.b64encode(f"{BILLPLZ_API_KEY}:".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}"}

        print(f"📡 {method} {url}")
        if data:
            print(f"📤 Payload: {json.dumps(data, indent=2)}")

        if method == "POST":
            response = requests.post(url, data=data, headers=headers)
        elif method == "PUT":
            response = requests.put(url, data=data, headers=headers)
        else:
            response = requests.get(url, headers=headers)

        try:
            result = response.json()
        except:
            result = {"raw_text": response.text}

        print(f"📥 Response ({response.status_code}): {json.dumps(result, indent=2)}")
        return response.status_code, result

# ------------------------------ HTTP GET ------------------------------
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        if path == "/":
            return self.serve_dashboard()
        elif path == "/pay":
            self.handle_create_bill(query)
        elif path == "/create-payment-form":
            self.handle_create_payment_form(query)
        elif path == "/create-payment-order":
            self.handle_create_payment_order(query)
        elif path == "/thankyou":
            self.handle_thankyou(query)
        elif path == "/api/bills":
            self.send_json_response(200, load_data("bills"))
        elif path == "/api/payment-form":  
            self.send_json_response(200, load_data("payment_form"))
        elif path == "/api/payment-orders":
            self.send_json_response(200, load_data("payment_orders"))
        elif path == "/api/callbacks":
            self.send_json_response(200, load_data("callbacks"))
        elif path.startswith("/api/bill/"):
            bill_id = path.split("/")[-1]
            self.get_bill_status(bill_id)
        else:
            self.send_json_response(404, {"error": "Endpoint not found"})

# ------------------------------ HTTP POST ------------------------------
    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        if path == "/callback":
            self.handle_callback(body)
        elif path == "/payment-order-callback":
            self.handle_payment_order_callback(body)
        else:
            self.send_json_response(404, {"error": "Endpoint not found"})


# ========================================================================================================
# Handlers
# ========================================================================================================
    def serve_dashboard(self):
        try:
            with open("index.html", "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_html_response("""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"><title>Dashboard Not Found</title></head>
            <body><h1>Dashboard File Not Found</h1></body>
            </html>
            """)

    def handle_create_bill(self, query):
        name = query.get("name", ["Anonymous"])[0]
        email = query.get("email", ["test@example.com"])[0]
        amount_rm = query.get("amount", [""])[0]
        description = query.get("description", ["Payment"])[0]

        try:
            amount_cents = str(int(float(amount_rm) * 100))
        except:
            amount_cents = "100"

        payload = {
            "collection_id": COLLECTION_ID,
            "email": email,
            "name": name,
            "amount": amount_cents,
            "description": description,
            "callback_url": f"{CALLBACK_BASE_URL}/callback",
            "redirect_url": f"{CALLBACK_BASE_URL}/thankyou"
        }

        status_code, result = self.make_billplz_request("bills", "POST", payload, version="v3")

        save_data("bills", {
            "type": "bill",
            "bill_id": result.get("id"),
            "name": name,
            "email": email,
            "amount_rm": amount_rm,
            "description": description,
            "response": result,
            "status_code": status_code})

        if status_code == 200 and "url" in result:
            self.send_response(302)
            self.send_header("Location", result["url"])
            self.end_headers()
        else:
            self.send_json_response(status_code, result)

    def handle_create_payment_form(self, query):
        title = query.get("title", ["Payment Form"])[0]
        description = query.get("description", ["Accept payments"])[0]
        amount_rm = query.get("amount", ["1"])[0]

        try:
            amount_cents = str(int(float(amount_rm) * 100))
        except:
            amount_cents = "100"
        
        payload = {
            "title": title,
            "description": description,
            "amount": amount_cents,
            "fixed_amount": True
        }


        status_code, result = self.make_billplz_request("open_collections", "POST", payload, version="v4")

        save_data("payment_form", {"type": "payment_form", "request": payload, "response": result, "status_code": status_code})

        if status_code == 200 and "url" in result:
            html = f"""
          <!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8">
            <title>Payment Form Created</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
                .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                a {{ color: #007bff; text-decoration: none; }}
                button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 10px 5px; }}
            </style>
            </head>
            <body>
            <div class="container">
                <h1>✅ Payment Form Created!</h1>
                <div class="success">
                    Form ID: {result.get('id', 'N/A')}<br>
                    Title: {title}<br>
                    Amount: RM {amount_rm}<br>
                    Form URL: <a href="{result.get('url', '')}" target="_blank">{result.get('url', '')}</a>
                </div>
                <button onclick="window.open('{result.get('url', '')}', '_blank')">Test Payment Form</button>
                <button onclick="window.location.href='/'">Back to Dashboard</button>
            </div>
            </body>
            </html>
            """
            self.send_html_response(html)
        else:
            self.send_json_response(status_code, result)

    def handle_create_payment_order(self, query):
        try:
            recipient_name = query.get("recipient_name", [""])[0]
            bank_code = query.get("bank_code", [""])[0]
            account_number = query.get("account_number", [""])[0]
            total_rm = query.get("amount", ["1"])[0]
            description = query.get("description", ["Payment"])[0]

            total_cents = int(float(total_rm) * 100) if total_rm else 100

            # Epoch timestamp and checksum
            epoch = int(time.time())
            raw_string = f"{PAYMENT_ORDER_COLLECTION_ID}{account_number}{total_cents}{epoch}"
            checksum = hmac.new(XSIGNATURE_KEY.encode(), raw_string.encode(), hashlib.sha512).hexdigest()

            payload = {
                "payment_order_collection_id": PAYMENT_ORDER_COLLECTION_ID,
                "bank_code": bank_code,
                "bank_account_number": account_number,
                "name": recipient_name,
                "total": total_cents,
                "description": description,
                "epoch": epoch,
                "checksum": checksum
            }

            status_code, result = self.make_billplz_request("payment_orders", "POST", payload, version="v5")

            save_data("payment_orders", {
                "type": "payment_order",
                "request": payload,
                "response": result,
                "status_code": status_code
            })

            if status_code == 200:
                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                <meta charset="utf-8">
                <title>Payment Order Created</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                    .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
                    .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                    a {{ color: #007bff; text-decoration: none; }}
                    button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 10px 5px; }}
                </style>
                </head>
                <body>
                <div class="container">
                    <h1>✅ Payment Order Created!</h1>
                    <div class="success">
                        Order ID: {result.get('id', 'N/A')}<br>
                        Recipient: {recipient_name}<br>
                        Bank: {bank_code}<br>
                        Account: {account_number}<br>
                        Amount: RM {total_rm}
                    </div>
                    <button onclick="window.location.href='/'">Back to Dashboard</button>
                </div>
                </body>
                </html>
                """
                self.send_html_response(html)
            else:
                self.send_json_response(status_code, result)
        except Exception as e:
            self.send_json_response(500, {"error": str(e)})

# ========================================================================================================
    def handle_thankyou(self, query):
        # Extract Billplz callback query params
        bill_id = query.get("billplz[id]", ["N/A"])[0]
        paid = query.get("billplz[paid]", ["false"])[0]
        paid_at = query.get("billplz[paid_at]", ["N/A"])[0]
        paid_amount = query.get("billplz[amount]", ["0"])[0]
        paid_amount = f"{int(paid_amount) / 100:.2f}"  # Billplz amount is in cents

        # load bills.json and match bill_id
        try:
            with open("bills.json", "r") as f:
                bills = json.load(f)
        except:
            bills = []

        if isinstance(bills, dict):
            bills = [bills]

        # find bill by id
        bill = next((b for b in bills if b.get("bill_id") == bill_id), {})

        # fallback values
        name = bill.get("name", "N/A")
        email = bill.get("email", "N/A")
        amount_rm = bill.get("amount_rm", paid_amount)
        url = bill.get("response", {}).get("url", "N/A")

        # Payment status
        status = "Payment Successful ✅" if paid == "true" else "Payment Failed ❌"

        # HTML Response
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <title>Payment Result</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
            .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            .failed {{ background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            a {{ color: #007bff; text-decoration: none; }}
            button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 10px 5px; }}
        </style>
        </head>
        <body>
        <div class="container">
            <h1>{status}</h1>
            <div class="{ 'success' if paid == 'true' else 'failed' }">
                Bill ID: {bill_id}<br>
                Name: {name}<br>
                Email: {email}<br>
                Amount: RM {amount_rm}<br>
                Paid At: {paid_at}<br>
            </div>
            <button onclick="window.location.href='/'">Back to Dashboard</button>
            <button onclick="window.open('{url}', '_blank')">View Receipt</button>
        </div>
        </body>
        </html>
        """
        self.send_html_response(html)


    def handle_callback(self, body):
        parsed = urllib.parse.parse_qs(body)
        callback_data = {k: v[0] for k, v in parsed.items()}
        signature = self.headers.get("X-Signature", "")
        save_data("callbacks", {"type": "payment_callback", "data": callback_data, "signature": signature})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def handle_payment_order_callback(self, body):
        parsed = urllib.parse.parse_qs(body)
        callback_data = {k: v[0] for k, v in parsed.items()}
        save_data("callbacks", {"type": "payment_order_callback", "data": callback_data})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def get_bill_status(self, bill_id):
        status_code, result = self.make_billplz_request(f"bills/{bill_id}", version="v3")
        self.send_json_response(status_code, result)


# ========================================================================================================
# Initialize Data Files
# ========================================================================================================
def initialize_data_files():
    for file_path in DATA_FILES.values():
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                json.dump([], f)


# ========================================================================================================
# Main Server
# ========================================================================================================
if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))  # serve files from this folder
    server_address = ('', PORT)
    print("🚀 Enhanced Billplz Integration Server")
    print("=" * 50)
    
    # Initialize data files
    initialize_data_files()
    
    print(f"\n🌐 Server Configuration:")
    print(f"   Port: {PORT}")
    print(f"   Base URL: http://127.0.0.1:{PORT}")
    print(f"   Callback URL: {CALLBACK_BASE_URL}")
    print(f"   Collection ID: {COLLECTION_ID}")
    print(f"   Payment Order Collection ID: {PAYMENT_ORDER_COLLECTION_ID}")
    
    print(f"\n🔧 Data Storage:")
    for data_type, file_path in DATA_FILES.items():
        print(f"   {data_type}: {file_path}")
    
    print("\n" + "=" * 50)
    print(f"🎯 Starting server at http://127.0.0.1:{PORT}")
    print("Press Ctrl+C to stop")

    try:
        httpd = HTTPServer(("0.0.0.0", PORT), EnhancedBillplzHandler)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
        httpd.server_close()