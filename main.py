import os
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import httpx

app = FastAPI()

# CORS для Netlify
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SendCodeRequest(BaseModel):
    phone: str

class VerifyRequest(BaseModel):
    sessionId: str
    code: str

# Получить подключение к БД
def get_db():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        cursor_factory=RealDictCursor
    )

# Создать таблицу
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            code TEXT NOT NULL,
            verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '15 minutes'
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database ready")

# API: отправка кода
@app.post("/api/send-code")
async def send_code(request: SendCodeRequest):
    phone = request.phone
    if not phone:
        raise HTTPException(status_code=400, detail="Phone required")
    
    code = str(secrets.randbelow(900000) + 100000)
    session_id = secrets.token_hex(16)
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions (session_id, phone, code) VALUES (%s, %s, %s)",
        (session_id, phone, code)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    site_url = os.getenv("SITE_URL", "https://твой-сайт.netlify.app")
    sent = await send_telegram(phone, code, session_id, site_url)
    
    return {"success": sent, "sessionId": session_id}

# API: проверка статуса
@app.get("/api/check-session/{session_id}")
async def check_session(session_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT verified FROM sessions WHERE session_id = %s AND expires_at > NOW()",
        (session_id,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if row:
        return {"verified": row["verified"]}
    return {"verified": False}

# API: авто-верификация
@app.post("/api/auto-verify")
async def auto_verify(request: VerifyRequest):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET verified = TRUE WHERE session_id = %s AND code = %s AND verified = FALSE",
        (request.sessionId, request.code)
    )
    conn.commit()
    affected = cur.rowcount
    cur.close()
    conn.close()
    
    return {"success": affected > 0}

# API: статистика
@app.get("/api/stats")
async def get_stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sessions WHERE verified = TRUE")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return {"total": row["count"] if row else 0}

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# Отправка в Telegram
async def send_telegram(phone: str, code: str, session_id: str, site_url: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print(f"DEMO: {phone} -> {code}")
        return True
    
    link = f"{site_url}/?sessionId={session_id}&code={code}"
    message = f"🔐 НОВЫЙ ЗАПРОС\n📱 {phone}\n🔑 {code}\n✅ [ПОДТВЕРДИТЬ]({link})"
    
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            })
            return resp.json().get("ok", False)
        except:
            return False

# Запуск
@app.on_event("startup")
async def startup():
    init_db()
    print("🚀 FastAPI on Render")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port) 
