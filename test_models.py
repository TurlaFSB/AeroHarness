import urllib.request
import json
import os

api_key = ""
with open("run.py") as f:
    for line in f:
        if "GEMINI_API_KEY" in line and "=" in line:
            api_key = line.split("=")[1].strip().strip('"').strip("'")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as response:
    models = json.loads(response.read().decode())
    for m in models.get("models", []):
        if "gemini" in m["name"]:
            print(m["name"])
