import logging
import os
import json
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== Configuration ==========
# Get environment variables (Railway compatible)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = json.loads(os.environ.get("ADMIN_IDS", "[]"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "data/broadcast.json"))

# Ensure data directory exists
DATABASE_PATH.parent.mkdir(exist_ok=True)

# ========== Database Management ==========
class Database:
    """Handle database operations"""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.data = self._load_default_data()
        self.load()
    
    def _load_default_data(self) -> Dict[str, Any]:
        """Return default database structure"""
        return {
            "broadcast_channels": [],
            "admins": ADMIN_IDS,
            "stats": {
                "total_broadcasts": 0,
                "successful_broadcasts": 0,
                "failed_broadcasts": 0,
                "last_broadcast": None
            }
        }
    
    def load(self):
        """Load database from file"""
        try:
            if self.file_path.exists():
                with open(self.file_path, 'r') as f:
                    loaded_data = json.load(f)
                    # Merge with default structure to ensure all keys exist
                    self.data.update(loaded_data)
                    # Ensure admins list includes initial ADMIN_IDS
                    for admin_id in ADMIN_IDS:
                        if admin_id not in self.data["admins"]:
                            self.data["admins"].append(admin_id)
                logger.info(f"Database loaded from {self.file_path}")
            else:
                self.save()
                logger.info(f"Created new database at {self.file_path}")
        except Exception as e:
            logger.error(f"Error loading database: {e}")
            self.save()  # Save default structure
    
    def save(self):
        """Save database to file"""
        try:
            with open(self.file_path, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
            logger.debug(f"Database saved to {self.file_path}")
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    def add_channel(self, channel_data: Dict):
        """Add a new broadcast channel"""
        if not any(str(ch["id"]) == str(channel_data["id"]) 
                  for ch in self.data["broadcast_channels"]):
            channel_data["added_date"] = datetime.now().isoformat()
            self.data["broadcast_channels"].append(channel_data)
            self.save()
            return True
        return False
    
    def remove_channel(self, channel_id: str):
        """Remove a channel by ID"""
        initial_count = len(self.data["broadcast_channels"])
        self.data["broadcast_channels"] = [
            ch for ch in self.data["broadcast_channels"] 
            if str(ch["id"]) != str(channel_id)
        ]
        if len(self.data["broadcast_channels"]) < initial_count:
            self.save()
            return True
        return False
    
    def get_channels(self) -> List[Dict]:
        """Get all broadcast channels"""
        return self.data["broadcast_channels"]
    
    def get_channel(self, channel_id: str) -> Dict:
        """Get specific channel by ID"""
        for channel in self.data["broadcast_channels"]:
            if str(channel["id"]) == str(channel_id):
                return channel
        return {}
    
    def add_admin(self, user_id: int):
        """Add a new admin"""
        if user_id not in self.data["admins"]:
            self.data["admins"].append(user_id)
            self.save()
            return True
        return False
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.data["admins"]
    
    def update_stats(self, success_count: int, total_count: int):
        """Update broadcast statistics"""
        self.data["stats"]["total_broadcasts"] += 1
        self.data["stats"]["successful_broadcasts"] += success_count
        self.data["stats"]["failed_broadcasts"] += (total_count - success_count)
        self.data["stats"]["last_broadcast"] = datetime.now().isoformat()
        self.save()

# Initialize database
db = Database(DATABASE_PATH)

# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    
    if db.is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
            [InlineKeyboardButton("📋 View Channels", callback_data="view_channels")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
            [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "👑 *Broadcast Bot Admin Panel*\n\n"
            "Select an option:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🚫 *Access Denied*\n\n"
            "This bot is only accessible to administrators.",
            parse_mode="Markdown"
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not db.is_admin(user_id):
        await query.edit_message_text("🚫 You are not authorized!")
        return
    
    # Main menu options
    if query.data == "main_menu":
        await show_main_menu(query)
    
    elif query.data == "add_channel":
        await query.edit_message_text(
            "*➕ Add Broadcast Channel*\n\n"
            "To add a channel:\n"
            "1. Add me as *Administrator* to your channel\n"
            "2. Send me:\n"
            "   • Channel @username\n"
            "   OR\n"
            "   • Forward any message from the channel\n\n"
            "I will verify my admin status and add it.",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_channel"] = True
    
    elif query.data == "view_channels":
        channels = db.get_channels()
        if not channels:
            await query.edit_message_text("📭 *No channels added yet.*", parse_mode="Markdown")
        else:
            channel_list = "\n".join(
                [f"• `{ch['id']}` - {ch.get('title', 'Unknown')}" 
                 for ch in channels]
            )
            await query.edit_message_text(
                f"*📋 Broadcast Channels ({len(channels)})*\n\n{channel_list}",
                parse_mode="Markdown"
            )
    
    elif query.data == "broadcast":
        channels = db.get_channels()
        if not channels:
            await query.edit_message_text(
                "❌ *No channels to broadcast to!*\n"
                "Add channels first using '➕ Add Channel'",
                parse_mode="Markdown"
            )
            return
        
        await query.edit_message_text(
            f"*📢 Broadcast Message*\n\n"
            f"Channels: {len(channels)}\n\n"
            f"Send me the message you want to broadcast.\n"
            f"I support all message types:\n"
            f"• Text\n• Photos\n• Videos\n• Documents\n• etc.",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_broadcast"] = True
    
    elif query.data == "stats":
        stats = db.data["stats"]
        channels = db.get_channels()
        
        stats_text = (
            f"*📊 Bot Statistics*\n\n"
            f"• Total Channels: {len(channels)}\n"
            f"• Total Broadcasts: {stats['total_broadcasts']}\n"
            f"• Successful: {stats['successful_broadcasts']}\n"
            f"• Failed: {stats['failed_broadcasts']}\n"
            f"• Last Broadcast: {stats['last_broadcast'] or 'Never'}"
        )
        
        keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="main_menu")]]
        await query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif query.data == "settings":
        await show_settings_menu(query)
    
    elif query.data == "remove_channel_menu":
        await show_remove_channel_menu(query)
    
    elif query.data.startswith("remove_channel_"):
        channel_id = query.data.replace("remove_channel_", "")
        if db.remove_channel(channel_id):
            await query.edit_message_text(f"✅ Channel `{channel_id}` removed!", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Channel not found!")
    
    elif query.data == "add_admin_menu":
        await query.edit_message_text(
            "*👥 Add Admin*\n\n"
            "Send me the user ID to add as admin:\n"
            "`/addadmin 123456789`",
            parse_mode="Markdown"
        )

async def show_main_menu(query):
    """Show the main admin menu"""
    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
        [InlineKeyboardButton("📋 View Channels", callback_data="view_channels")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ]
    await query.edit_message_text(
        "👑 *Broadcast Bot Admin Panel*\n\n"
        "Select an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_settings_menu(query):
    """Show settings menu"""
    keyboard = [
        [InlineKeyboardButton("🗑 Remove Channel", callback_data="remove_channel_menu")],
        [InlineKeyboardButton("👥 Add Admin", callback_data="add_admin_menu")],
        [InlineKeyboardButton("📋 List Admins", callback_data="list_admins")],
        [InlineKeyboardButton("« Back to Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        "*⚙️ Settings*\n\n"
        "Manage bot settings:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_remove_channel_menu(query):
    """Show channel removal menu"""
    channels = db.get_channels()
    if not channels:
        await query.edit_message_text("📭 No channels to remove!")
        return
    
    keyboard = []
    for channel in channels[:50]:  # Limit to 50 channels due to Telegram limits
        keyboard.append([
            InlineKeyboardButton(
                f"❌ {channel.get('title', 'Unknown')[:20]}",
                callback_data=f"remove_channel_{channel['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("« Back to Settings", callback_data="settings")])
    
    await query.edit_message_text(
        "*🗑 Remove Channel*\n\n"
        "Select a channel to remove:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("🚫 You are not authorized!")
        return
    
    # Handle channel addition
    if context.user_data.get("awaiting_channel"):
        await process_channel_addition(update, context)
    
    # Handle broadcast message
    elif context.user_data.get("awaiting_broadcast"):
        await process_broadcast(update, context)
    
    else:
        # Default response
        await start(update, context)

async def process_channel_addition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process channel addition request"""
    channel_id = None
    channel_title = "Unknown"
    
    # Check forwarded message from channel
    if update.message.forward_from_chat:
        if update.message.forward_from_chat.type in ["channel", "supergroup"]:
            channel_id = update.message.forward_from_chat.id
            channel_title = update.message.forward_from_chat.title
    
    # Check text message with channel info
    elif update.message.text:
        text = update.message.text.strip()
        # Handle @username or channel ID
        if text.startswith("@"):
            channel_title = text
            channel_id = text
        elif text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            channel_id = int(text)
            channel_title = f"Channel {text}"
    
    if channel_id:
        await verify_and_add_channel(update, context, channel_id, channel_title)
    else:
        await update.message.reply_text(
            "❌ *Invalid Input*\n\n"
            "Please send:\n"
            "• Channel @username\n"
            "• Channel ID\n"
            "• Forward a message from the channel",
            parse_mode="Markdown"
        )
    
    context.user_data.pop("awaiting_channel", None)

async def verify_and_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                               channel_id, channel_title):
    """Verify bot is admin and add channel"""
    try:
        # Try to get chat info to verify bot is admin
        try:
            chat = await context.bot.get_chat(channel_id)
            channel_title = chat.title or channel_title
            
            # Check if bot is admin
            chat_member = await context.bot.get_chat_member(channel_id, context.bot.id)
            is_admin = chat_member.status in ["administrator", "creator"]
            
            if not is_admin:
                await update.message.reply_text(
                    f"❌ *Not Admin*\n\n"
                    f"I'm not an administrator in `{channel_title}`\n"
                    f"Please make me admin with necessary permissions.",
                    parse_mode="Markdown"
                )
                return
        
        except Exception as e:
            logger.warning(f"Could not verify admin status: {e}")
            # Still add channel but with warning
            await update.message.reply_text(
                f"⚠️ *Could not verify admin status*\n\n"
                f"Adding channel anyway. Please ensure I'm admin "
                f"or broadcasts may fail.\n\n"
                f"Error: {str(e)[:100]}",
                parse_mode="Markdown"
            )
        
        # Add to database
        channel_data = {
            "id": channel_id,
            "title": channel_title,
            "username": getattr(chat, 'username', None) if 'chat' in locals() else None
        }
        
        if db.add_channel(channel_data):
            await update.message.reply_text(
                f"✅ *Channel Added Successfully!*\n\n"
                f"• Name: {channel_title}\n"
                f"• ID: `{channel_id}`\n\n"
                f"Total channels: {len(db.get_channels())}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"⚠️ *Channel Already Exists*\n\n"
                f"`{channel_title}` is already in the broadcast list.",
                parse_mode="Markdown"
            )
    
    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        await update.message.reply_text(
            f"❌ *Error Adding Channel*\n\n"
            f"Make sure:\n"
            f"1. I'm added to the channel\n"
            f"2. Channel ID/username is correct\n"
            f"3. For private channels, use the numeric ID",
            parse_mode="Markdown"
        )

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process broadcast to all channels"""
    channels = db.get_channels()
    
    if not channels:
        await update.message.reply_text("❌ No channels to broadcast to!")
        context.user_data.pop("awaiting_broadcast", None)
        return
    
    # Send initial status
    status_msg = await update.message.reply_text(
        f"🔄 *Starting Broadcast...*\n\n"
        f"• Total channels: {len(channels)}\n"
        f"• Status: Preparing",
        parse_mode="Markdown"
    )
    
    success_count = 0
    failed_channels = []
    failed_reasons = []
    
    # Broadcast to each channel
    for index, channel in enumerate(channels, 1):
        try:
            # Update status message every 5 channels
            if index % 5 == 0 or index == len(channels):
                await status_msg.edit_text(
                    f"🔄 *Broadcasting...*\n\n"
                    f"• Progress: {index}/{len(channels)}\n"
                    f"• Successful: {success_count}\n"
                    f"• Failed: {len(failed_channels)}",
                    parse_mode="Markdown"
                )
            
            # Send message based on type
            await send_to_channel(update.message, context.bot, channel["id"])
            success_count += 1
            
        except Exception as e:
            logger.error(f"Failed to send to {channel.get('title', 'Unknown')}: {e}")
            failed_channels.append(channel.get('title', f"ID: {channel['id']}"))
            failed_reasons.append(str(e)[:100])
    
    # Update statistics
    db.update_stats(success_count, len(channels))
    
    # Send final report
    await send_broadcast_report(update, status_msg, success_count, 
                               len(channels), failed_channels, failed_reasons)
    
    context.user_data.pop("awaiting_broadcast", None)

async def send_to_channel(message, bot, chat_id):
    """Send message to a specific channel"""
    if message.text:
        await bot.send_message(chat_id=chat_id, text=message.text)
    elif message.photo:
        await bot.send_photo(
            chat_id=chat_id,
            photo=message.photo[-1].file_id,
            caption=message.caption
        )
    elif message.video:
        await bot.send_video(
            chat_id=chat_id,
            video=message.video.file_id,
            caption=message.caption
        )
    elif message.document:
        await bot.send_document(
            chat_id=chat_id,
            document=message.document.file_id,
            caption=message.caption
        )
    elif message.audio:
        await bot.send_audio(
            chat_id=chat_id,
            audio=message.audio.file_id,
            caption=message.caption
        )
    else:
        # For any other message type, try to copy
        await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )

async def send_broadcast_report(update, status_msg, success_count, total_count, 
                               failed_channels, failed_reasons):
    """Send broadcast completion report"""
    report = (
        f"✅ *Broadcast Complete!*\n\n"
        f"• Total: {total_count}\n"
        f"• Success: {success_count}\n"
        f"• Failed: {total_count - success_count}\n"
        f"• Success Rate: {(success_count/total_count*100):.1f}%\n"
    )
    
    if failed_channels:
        report += f"\n*Failed Channels ({len(failed_channels)}):*\n"
        for i,
