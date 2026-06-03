import os
import secrets
import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime, timedelta
from telegram import send_telegram_code

app = FastAPI()

# CORS для Netlify
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # для теста, потом ограничь *.netlify.app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели данных
class SendCodeRequest(BaseModel):
    phone: str

class VerifyRequest(BaseModel):
    sessionId: str
    code: str

# Подключение к БД
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()

# Инициализация таблиц
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            code TEXT NOT NULL,
            verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '15 minutes'
        )
    """)
    await conn.close()
    print("✅ Database ready")

# API: отправка кода
@app.post("/api/send-code")
async def send_code(request: SendCodeRequest):
    phone = request.phone
    
    if not phone:
        raise HTTPException(status_code=400, detail="Phone required")
    
    code = str(secrets.randbelow(900000) + 100000)
    session_id = secrets.token_hex(16)
    
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO sessions (session_id, phone, code)
        VALUES ($1, $2, $3)
    """, session_id, phone, code)
    await conn.close()
    
    site_url = os.getenv("SITE_URL", "http://localhost:3000")
    sent = await send_telegram_code(phone, code, session_id, site_url)
    
    return {"success": sent, "sessionId": session_id}

# API: проверка статуса
@app.get("/api/check-session/{session_id}")
async def check_session(session_id: str):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("""
        SELECT verified FROM sessions 
        WHERE session_id = $1 AND expires_at > NOW()
    """, session_id)
    await conn.close()
    
    if row:
        return {"verified": row["verified"]}
    return {"verified": False}

# API: авто-верификация
@app.post("/api/auto-verify")
async def auto_verify(request: VerifyRequest):
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute("""
        UPDATE sessions SET verified = TRUE 
        WHERE session_id = $1 AND code = $2 AND verified = FALSE
    """, request.sessionId, request.code)
    await conn.close()
    
    # если обновилась хотя бы одна строка
    if "UPDATE 1" in result:
        return {"success": True}
    return {"success": False}

# API: статистика
@app.get("/api/stats")
async def get_stats():
    conn = await asyncpg.connect(DATABASE_URL)
    count = await conn.fetchval("SELECT COUNT(*) FROM sessions WHERE verified = TRUE")
    await conn.close()
    return {"total": count or 0}

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# Запуск
@app.on_event("startup")
async def startup():
    await init_db()
    print("🚀 FastAPI server running")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)
