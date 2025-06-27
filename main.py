# -*- coding: utf-8 -*-
"""
Created on Thu Jun 26 22:30:46 2025

@author: sheik
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import json
import os

app = FastAPI()
DB_FILE = "messages.json"

if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump([], f)

class CoreMsg(BaseModel):
    to: str
    from_: str  # sender's public key hash
    payload: str
    timestamp: str
    msg_id: str = ""

def save_message(msg):
    try:
        with open(DB_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    except FileNotFoundError:
        data = []

    data.append(msg)

    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_messages():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def delete_messages_for(recipient_id: str):
    with open(DB_FILE, "r+") as f:
        data = json.load(f)
        remaining = [m for m in data if m["to"] != recipient_id]
        f.seek(0)
        f.truncate()
        json.dump(remaining, f, indent=2)

@app.post("/send")
async def send_message(msg: CoreMsg):
    if not msg.to or not msg.payload:
        raise HTTPException(status_code=400, detail="Missing fields")
    msg_dict = msg.dict()
    msg_dict["from"] = msg_dict.pop("from_")
    save_message(msg_dict)
    return {"status": "ok", "saved_at": datetime.utcnow().isoformat()}
from fastapi.responses import JSONResponse
from urllib.parse import unquote_plus
from urllib.parse import unquote
@app.get("/fetch")
async def fetch_messages(recipient_id: str):
    recipient_id = unquote(recipient_id).strip()
    messages = load_messages()
    user_msgs = [m for m in messages if m.get("to", "").strip() == recipient_id]
    if not user_msgs:
        return JSONResponse(
            content={"detail": "Not Found", "recipient_id_received": recipient_id},
            status_code=404
        )
    delete_messages_for(recipient_id)
    return {"recipient_id_received": recipient_id, "messages": user_msgs}

@app.get("/debug_all")
def debug_all():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try:
                data = json.load(f)
                return JSONResponse(content=data)
            except json.JSONDecodeError:
                return JSONResponse(content={"error": "Invalid JSON"}, status_code=500)
    return JSONResponse(content={"error": "File not found"}, status_code=404)
@app.get("/debug_users")
def debug_all_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try:
                data = json.load(f)

                users = set()
                for msg in data:
                    users.add(msg.get("to"))
                    users.add(msg.get("from_") or msg.get("from"))  # support both

                return JSONResponse(content={"users": list(users)})
            except json.JSONDecodeError:
                return JSONResponse(content={"error": "Invalid JSON"}, status_code=500)

    return JSONResponse(content={"error": "File not found"}, status_code=404)

