import os
import requests

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("-CHAT_ID")
MESSAGE = os.getenv("MESSAGE", "Default message")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": MESSAGE}

resp = requests.post(url, data=payload)
print("Status:", resp.status_code, resp.text)

