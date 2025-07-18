from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from urllib.parse import unquote
import json
import os
import sqlite3
from typing import List

app = FastAPI()

# ─── FILE-BASED MESSAGE STORAGE ─────────────────────────────
DB_FILE = "messages.json"
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump([], f)
        
class CoreMsg(BaseModel):
    to: str
    from_: str
    sender_username: str
    payload: str
    timestamp: str
    msg_id: str = ""


def save_message(msg):
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    data.append(msg)
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_messages():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def delete_messages_for(recipient: str):
    with open(DB_FILE, "r+") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []
        remaining = [m for m in data if m.get("to") != recipient]
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
    await manager.send_personal_message(msg_dict, msg_dict["to"])
    return {"status": "ok", "saved_at": datetime.utcnow().isoformat()}

@app.get("/fetch")
async def fetch_messages(recipient: str):
    recipient = unquote(recipient).strip()
    messages = load_messages()
    user_msgs = [m for m in messages if m.get("to", "").strip() == recipient]
    if not user_msgs:
        return JSONResponse(content={"detail": "Not Found", "recipient": recipient}, status_code=404)
    delete_messages_for(recipient)
    return {"recipient": recipient, "messages": user_msgs}

@app.get("/debug_all")
def debug_all():
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/debug_users")
def debug_all_users():
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
        users = set()
        for msg in data:
            users.add(msg.get("to"))
            users.add(msg.get("from") or msg.get("from_"))
        return JSONResponse(content={"users": list(users)})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

# ─── SQLITE USERNAME-TO-PUBKEY STORAGE ──────────────────────
USER_DB = "users.db"

def init_user_db():
    conn = sqlite3.connect(USER_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            public_key TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def store_user(username: str, public_key: str) -> bool:
    try:
        conn = sqlite3.connect(USER_DB)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users (username, public_key) VALUES (?, ?)", (username, public_key))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("[DB ERROR] store_user:", e)
        return False

def get_public_key(username: str) -> str | None:
    try:
        conn = sqlite3.connect(USER_DB)
        c = conn.cursor()
        c.execute("SELECT public_key FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print("[DB ERROR] get_public_key:", e)
        return None

class UserCreate(BaseModel):
    username: str
    public_key: str

@app.post("/user")
async def create_user(user: UserCreate):
    success = store_user(user.username.strip(), user.public_key.strip())
    if success:
        return {"status": "ok"}
    return JSONResponse(content={"error": "Failed to store user"}, status_code=500)

@app.get("/user/{username}")
async def get_user(username: str):
    pubkey = get_public_key(username.strip())
    if pubkey:
        return {"username": username, "public_key": pubkey}
    return JSONResponse(content={"error": "User not found"}, status_code=404)

@app.get("/user_exists/{username}")
async def user_exists(username: str):
    pubkey = get_public_key(username.strip())
    return {"exists": bool(pubkey)}

# ─── WEBSOCKET CONNECTION HANDLER (USERNAME-BASED) ──────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, List[WebSocket]] = {}

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        if username not in self.active_connections:
            self.active_connections[username] = []
        self.active_connections[username].append(websocket)

    def disconnect(self, username: str, websocket: WebSocket):
        if username in self.active_connections:
            self.active_connections[username].remove(websocket)
            if not self.active_connections[username]:
                del self.active_connections[username]

    async def send_personal_message(self, message: dict, username: str):
        if username in self.active_connections:
            for conn in self.active_connections[username]:
                await conn.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(username, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(username, websocket)

# ─── INIT ───────────────────────────────────────────────────
init_user_db()
