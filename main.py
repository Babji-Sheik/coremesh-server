# from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
# from fastapi.responses import JSONResponse
# from pydantic import BaseModel
# from datetime import datetime
# from urllib.parse import unquote
# import json
# import os
# import sqlite3
# from typing import List

# app = FastAPI()

# # ─── FILE-BASED MESSAGE STORAGE ─────────────────────────────
# DB_FILE = "messages.json"
# if not os.path.exists(DB_FILE):
#     with open(DB_FILE, "w") as f:
#         json.dump([], f)

# class CoreMsg(BaseModel):
#     to: str
#     from_: str
#     payload: str
#     timestamp: str
#     msg_id: str = ""

# def save_message(msg):
#     try:
#         with open(DB_FILE, "r") as f:
#             try:
#                 data = json.load(f)
#             except json.JSONDecodeError:
#                 data = []
#     except FileNotFoundError:
#         data = []

#     data.append(msg)
#     with open(DB_FILE, "w") as f:
#         json.dump(data, f, indent=2)

# def load_messages():
#     with open(DB_FILE, "r") as f:
#         return json.load(f)

# def delete_messages_for(recipient_id: str):
#     with open(DB_FILE, "r+") as f:
#         data = json.load(f)
#         remaining = [m for m in data if m["to"] != recipient_id]
#         f.seek(0)
#         f.truncate()
#         json.dump(remaining, f, indent=2)

# @app.post("/send")
# async def send_message(msg: CoreMsg):
#     if not msg.to or not msg.payload:
#         raise HTTPException(status_code=400, detail="Missing fields")
#     msg_dict = msg.dict()
#     msg_dict["from"] = msg_dict.pop("from_")
#     save_message(msg_dict)
#     await manager.send_personal_message(msg_dict, msg_dict["to"])
#     return {"status": "ok", "saved_at": datetime.utcnow().isoformat()}

# @app.get("/fetch")
# async def fetch_messages(recipient_id: str):
#     recipient_id = unquote(recipient_id).strip()
#     messages = load_messages()
#     user_msgs = [m for m in messages if m.get("to", "").strip() == recipient_id]
#     if not user_msgs:
#         return JSONResponse(
#             content={"detail": "Not Found", "recipient_id_received": recipient_id},
#             status_code=404
#         )
#     delete_messages_for(recipient_id)
#     return {"recipient_id_received": recipient_id, "messages": user_msgs}

# @app.get("/debug_all")
# def debug_all():
#     if os.path.exists(DB_FILE):
#         with open(DB_FILE, "r") as f:
#             try:
#                 data = json.load(f)
#                 return JSONResponse(content=data)
#             except json.JSONDecodeError:
#                 return JSONResponse(content={"error": "Invalid JSON"}, status_code=500)
#     return JSONResponse(content={"error": "File not found"}, status_code=404)

# @app.get("/debug_users")
# def debug_all_users():
#     if os.path.exists(DB_FILE):
#         with open(DB_FILE, "r") as f:
#             try:
#                 data = json.load(f)
#                 users = set()
#                 for msg in data:
#                     users.add(msg.get("to"))
#                     users.add(msg.get("from_") or msg.get("from"))
#                 return JSONResponse(content={"users": list(users)})
#             except json.JSONDecodeError:
#                 return JSONResponse(content={"error": "Invalid JSON"}, status_code=500)
#     return JSONResponse(content={"error": "File not found"}, status_code=404)

# # ─── SQLITE USERNAME-TO-PUBKEY STORAGE ──────────────────────
# USER_DB = "users.db"

# def init_user_db():
#     conn = sqlite3.connect(USER_DB)
#     c = conn.cursor()
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS users (
#             username TEXT PRIMARY KEY,
#             public_key TEXT NOT NULL
#         )
#     """)
#     conn.commit()
#     conn.close()

# def store_user(username: str, public_key: str) -> bool:
#     try:
#         conn = sqlite3.connect(USER_DB)
#         c = conn.cursor()
#         c.execute("INSERT OR REPLACE INTO users (username, public_key) VALUES (?, ?)", (username, public_key))
#         conn.commit()
#         conn.close()
#         return True
#     except Exception as e:
#         print("[DB ERROR] store_user:", e)
#         return False

# def get_public_key(username: str) -> str | None:
#     try:
#         conn = sqlite3.connect(USER_DB)
#         c = conn.cursor()
#         c.execute("SELECT public_key FROM users WHERE username = ?", (username,))
#         row = c.fetchone()
#         conn.close()
#         return row[0] if row else None
#     except Exception as e:
#         print("[DB ERROR] get_public_key:", e)
#         return None

# class UserCreate(BaseModel):
#     username: str
#     public_key: str

# @app.post("/user")
# async def create_user(user: UserCreate):
#     success = store_user(user.username.strip(), user.public_key.strip())
#     if success:
#         return {"status": "ok"}
#     return JSONResponse(content={"error": "Failed to store user"}, status_code=500)

# @app.get("/user/{username}")
# async def get_user(username: str):
#     pubkey = get_public_key(username.strip())
#     if pubkey:
#         return {"username": username, "public_key": pubkey}
#     return JSONResponse(content={"error": "User not found"}, status_code=404)

# @app.get("/user_exists/{username}")
# async def user_exists(username: str):
#     pubkey = get_public_key(username.strip())
#     return {"exists": bool(pubkey)}

# # ─── WEBSOCKET CONNECTION HANDLER ───────────────────────────
# class ConnectionManager:
#     def __init__(self):
#         self.active_connections: dict[str, List[WebSocket]] = {}

#     async def connect(self, user_id: str, websocket: WebSocket):
#         await websocket.accept()
#         if user_id not in self.active_connections:
#             self.active_connections[user_id] = []
#         self.active_connections[user_id].append(websocket)

#     def disconnect(self, user_id: str, websocket: WebSocket):
#         if user_id in self.active_connections:
#             self.active_connections[user_id].remove(websocket)
#             if not self.active_connections[user_id]:
#                 del self.active_connections[user_id]

#     async def send_personal_message(self, message: dict, user_id: str):
#         if user_id in self.active_connections:
#             for conn in self.active_connections[user_id]:
#                 await conn.send_json(message)

# manager = ConnectionManager()

# @app.websocket("/{recipient_id}")
# async def websocket_endpoint(websocket: WebSocket, recipient_id: str):
#     await manager.connect(recipient_id, websocket)
#     try:
#         while True:
#             await websocket.receive_text()  # keep alive
#     except WebSocketDisconnect:
#         manager.disconnect(recipient_id, websocket)

# # ─── INIT ───────────────────────────────────────────────────
# init_user_db()
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
app = FastAPI()
class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, pubkey: str, websocket: WebSocket):
        await websocket.accept()
        if pubkey not in self.connections:
            self.connections[pubkey] = []
        self.connections[pubkey].append(websocket)

    def disconnect(self, pubkey: str, websocket: WebSocket):
        if pubkey in self.connections:
            self.connections[pubkey].remove(websocket)
            if not self.connections[pubkey]:
                del self.connections[pubkey]

    async def send_to(self, recipient_key: str, message: str):
        if recipient_key in self.connections:
            for ws in self.connections[recipient_key]:
                await ws.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/{public_key}")
async def ws_endpoint(websocket: WebSocket, public_key: str):
    await manager.connect(public_key, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                obj = json.loads(data)
                to_key = obj["to"]
                message = obj["message"]
                await manager.send_to(to_key, f"[{public_key}] {message}")
            except Exception as e:
                await websocket.send_text(f"[ERROR] Invalid message format or routing failed: {e}")
    except WebSocketDisconnect:
        manager.disconnect(public_key, websocket)
