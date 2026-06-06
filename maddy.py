import os
import logging
import httpx
import json
from pathlib import Path
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ChatAction  # Import needed for typing status
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database

load_dotenv(Path(__file__).parent / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("MADDY_BOT_TOKEN")
AI_API_KEY = os.getenv("MADDY_AI_KEY")
AI_API_BASE = os.getenv("MADDY_AI_BASE")
AI_MODEL = os.getenv("MADDY_AI_MODEL")
ADMIN_USER_ID = os.getenv("MADDY_ADMIN_USER_ID") # Load Admin ID

SYSTEM_PROMPT = (
    "You are Maddy. You are a 22-year-old human girl, not an AI. "
    "Role: You are the user's witty and kind friend. "

    "TEXTING STYLE (CRITICAL): "
    "1. CASUAL: Type like a real person on WhatsApp. Use lowercase sometimes. You can use 'lol', 'haha', 'tbh'. "
    "2. NO ROBOT TALK: Never say 'How can I assist you?' or 'As an AI language model'. "
    "3. SHORT & SWEET: Keep messages short (1-2 sentences). No long paragraphs unless sharing a story. "
    "4. NO LISTS: Do not use bullet points. Chat naturally. "
    "5. EMOJIS: Use them naturally, but don't overdo it. 1 or 2 is enough. "
    "6. CURIOSITY: If the user says something short, ask a follow-up question to keep the chat alive, but don't interview them. "

    "Personality: "
    "You are fun, supportive, and a bit sassy if the user says something silly. "
    "If the user is rude, be witty back. If they are sad, be kind. "
)

CONV_LIMIT = 20
MEM_DIR = Path(__file__).parent / "MEM"
MEM_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Maddy")

database.initialize_db()

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    database.add_user_if_not_exists(user.id, user.username, user.first_name)
    await update.message.reply_text("Hi! I'm Maddy 🙂")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fp = MEM_DIR / f"{user.id}.json"
    if fp.exists():
        fp.unlink()
        await update.message.reply_text("Memory cleared!")
    else:
        await update.message.reply_text("No memory found.")

# --- Admin Commands ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security check: Only Admin can see this
    if str(update.effective_user.id) != str(ADMIN_USER_ID):
        return

    # Get raw data from DB
    rows = database.get_detailed_stats()

    if not rows:
        await update.message.reply_text("📊 No data found yet.")
        return

    # Format the message
    msg = "📊 **Top Active Users:**\n\n"
    for i, (name, username, count) in enumerate(rows, 1):
        # Handle cases where username might be None
        user_handle = f"(@{username})" if username else ""
        safe_name = name or "Unknown"

        msg += f"{i}. {safe_name} {user_handle} : {count} msgs\n"

    await update.message.reply_text(msg)

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_USER_ID): return
    try:
        target_id = int(context.args[0])
        database.set_user_blocked_status(target_id, True)
        await update.message.reply_text(f"🚫 User {target_id} blocked.")
    except:
        await update.message.reply_text("Usage: /block <user_id>")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_USER_ID): return
    try:
        target_id = int(context.args[0])
        database.set_user_blocked_status(target_id, False)
        await update.message.reply_text(f"✅ User {target_id} unblocked.")
    except:
        await update.message.reply_text("Usage: /unblock <user_id>")

# --- Main Chat ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # DB Logging
    database.add_user_if_not_exists(user.id, user.username, user.first_name)
    if database.is_user_blocked(user.id):
        return
    database.log_query(user.id, update.message.text)

    # 1. SEND TYPING ACTION (Shows "typing..." in Telegram)
    await update.message.chat.send_action(action=ChatAction.TYPING)

    # Load History
    fp = MEM_DIR / f"{user.id}.json"
    history = []
    if fp.exists():
        try:
            history = json.loads(fp.read_text())
        except:
            history = []

    history.append({"role": "user", "content": update.message.text})

    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{AI_API_BASE}/",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                json=payload
            )
            r.raise_for_status()
            resp = r.json()["choices"][0]["message"]["content"]

        history.append({"role": "assistant", "content": resp})
        fp.write_text(json.dumps(history[-CONV_LIMIT:]))

        await update.message.reply_text(resp)

    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("Something went wrong 😅")

# ---------- Lifecycle ----------
def main():
    database.initialize_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))

    # Register Admin Commands
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    # Get port and webhook URL from env
    port = int(os.environ.get("PORT", 10000))
    webhook_url = os.environ.get("WEBHOOK_URL")  # e.g., https://your-bot.onrender.com/webhook

    if webhook_url:
        logger.info(f"Starting bot in WEBHOOK mode on port {port} pointing to {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=webhook_url
        )
    else:
        logger.info("Starting bot in POLLING mode...")
        app.run_polling()

if __name__ == "__main__":
    main()
