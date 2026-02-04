import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Get variables from Railway
BOT_TOKEN = os.environ["BOT_TOKEN"]  # Required - get from Railway
ADMIN_IDS = json.loads(os.environ.get("ADMIN_IDS", "[]"))  # Your Telegram ID

# Database file
db_file = Path("broadcast_data.json")

# Load database
if db_file.exists():
    with open(db_file, 'r') as f:
        data = json.load(f)
else:
    data = {"channels": [], "admins": ADMIN_IDS, "stats": {"total": 0}}

def save_db():
    with open(db_file, 'w') as f:
        json.dump(data, f, indent=2)

# ========== BOT FUNCTIONS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in data["admins"]:
        keyboard = [
            [InlineKeyboardButton("➕ Add Channel", callback_data="add")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
            [InlineKeyboardButton("📋 List Channels", callback_data="list")]
        ]
        await update.message.reply_text(
            "👑 Admin Panel",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("❌ Not authorized")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "add":
        await query.edit_message_text("Send me channel @username or forward message from channel")
        context.user_data["adding"] = True
    elif query.data == "broadcast":
        await query.edit_message_text("Send message to broadcast to all channels")
        context.user_data["broadcasting"] = True
    elif query.data == "list":
        channels = data["channels"]
        if channels:
            text = "📋 Channels:\n" + "\n".join([f"• {c['title']}" for c in channels])
        else:
            text = "No channels added"
        await query.edit_message_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in data["admins"]:
        return
    
    if context.user_data.get("adding"):
        channel_id = None
        if update.message.forward_from_chat:
            channel_id = update.message.forward_from_chat.id
            title = update.message.forward_from_chat.title
        elif update.message.text and update.message.text.startswith("@"):
            channel_id = update.message.text
            title = update.message.text
        
        if channel_id:
            data["channels"].append({"id": channel_id, "title": title})
            save_db()
            await update.message.reply_text(f"✅ Added: {title}")
        
        context.user_data.pop("adding", None)
    
    elif context.user_data.get("broadcasting"):
        channels = data["channels"]
        success = 0
        for channel in channels:
            try:
                await context.bot.copy_message(
                    chat_id=channel["id"],
                    from_chat_id=update.message.chat_id,
                    message_id=update.message.message_id
                )
                success += 1
            except:
                pass
        
        data["stats"]["total"] += 1
        save_db()
        await update.message.reply_text(f"✅ Sent to {success}/{len(channels)} channels")
        context.user_data.pop("broadcasting", None)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
