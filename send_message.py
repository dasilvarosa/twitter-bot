import os
import requests

TOKEN = os.getenv("8459510220:AAFa3BBWr1_UmQooBT-Sglrgx6kWN0a9qYo")
CHAT_ID = os.getenv("-4899509068")
MESSAGE = os.getenv("MESSAGE", "Default message")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": MESSAGE}

resp = requests.post(url, data=payload)
print("Status:", resp.status_code, resp.text)

