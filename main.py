import os
import asyncio
import json
import shutil
import sqlite3
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes
)

import database as db

# ========== CONFIGURATION ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
OWNER_ID = 8104850843
LOG_CHANNEL_ID = -10036720099488  # private log channel

# Forced channels
FORCED_CHANNELS = [
    {"name": "All Data Here", "link": "https://t.me/all_data_here", "id": -1003090922367},
    {"name": "OSINT Lookup", "link": "https://t.me/osint_lookup", "id": -1003698567122},
    {"name": "LEGEND CHATS", "link": "https://t.me/legend_chats_osint", "id": -1003672015073},
]

# Fake APIs
START_API = "https://bomber.kingcc.qzz.io/bomb"
SINGLE_API = "https://bomm.gauravcyber0.workers.dev/"
STOP_API = "https://bomber.kingcc.qzz.io/stop"
API_KEY = "urfaaan_omdivine"

# Bombing settings
INTERVAL_SECONDS = 30
MAX_DURATION_SECONDS = 24 * 3600
FREE_DAILY_LIMIT = 3
REFERRAL_BONUS_CYCLES = 5

# Branding
BRANDING = "\n\n⚡ Powered by NULL PROTOCOL"

# Conversation states
PHONE, DURATION = range(2)
ADMIN_BAN, ADMIN_UNBAN, ADMIN_DELETE, ADMIN_DM_USER, ADMIN_DM_MSG, ADMIN_BROADCAST, ADMIN_BULKDM = range(7)
# New states for pro features
SCHEDULE_DATE, SCHEDULE_TIME, REFERRAL_CODE, PREMIUM_DAYS, ADMIN_PREMIUM_USER, ADMIN_PREMIUM_DAYS = range(7, 13)
REFERRAL_JOIN, PREMIUM_GRANT, PREMIUM_REVOKE = range(13, 16)

# Active bombing sessions
active_bombs: Dict[int, asyncio.Task] = {}

# ========== HELPER FUNCTIONS ==========
def format_json_human(data):
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
    try:
        url = f"{START_API}?key={API_KEY}&numbar={phone}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

async def call_single_api(phone):
    try:
        url = f"{SINGLE_API}?phone={phone}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

async def call_stop_api(phone):
    try:
        url = f"{STOP_API}?key={API_KEY}&numbar={phone}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

async def check_force_join(user_id, context):
    for channel in FORCED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
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

    # Check if user has premium record; if not, create one (with referral code)
    if db.get_referral_code(user.id) is None:
        db.create_premium(user.id, days=0, referral_code=db.generate_referral_code(user.id))

    await show_main_menu(update, context)

async def show_main_menu(update, context, edit=False):
    user_id = update.effective_user.id
    premium = db.is_premium(user_id)
    keyboard = [
        [InlineKeyboardButton("💣 Bomber", callback_data="bomber")],
        [InlineKeyboardButton("📅 Schedule Bomb", callback_data="schedule_bomb")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("👥 Referrals", callback_data="referrals")],
    ]
    if not premium:
        keyboard.append([InlineKeyboardButton("💎 Upgrade to Premium", callback_data="premium_plans")])
    if db.is_admin(user_id, OWNER_ID):
        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
    keyboard.append([InlineKeyboardButton("ℹ️ Info", callback_data="info")])
    keyboard.append([InlineKeyboardButton("🆘 Help", callback_data="help")])

    text = "🔫 *Main Menu*" + BRANDING
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ---------- Profile ----------
async def profile(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    premium = db.is_premium(user_id)
    expiry = db.get_premium_expiry(user_id)
    total_bombs, total_cycles = db.get_stats(user_id)
    ref_count = db.get_referral_stats(user_id)
    ref_code = db.get_referral_code(user_id)

    if premium:
        premium_status = f"✅ Active until {expiry.strftime('%Y-%m-%d')}" if expiry else "✅ Active (lifetime?)"
    else:
        premium_status = "❌ Not active"

    text = (
        f"👤 *Your Profile*\n"
        f"🆔 ID: `{user_id}`\n"
        f"💎 Premium: {premium_status}\n"
        f"📊 Total Bombs: {total_bombs}\n"
        f"🔄 Total Cycles: {total_cycles}\n"
        f"👥 Referrals: {ref_count}\n\n"
        f"🔗 Your referral link:\n"
        f"`https://t.me/{(await context.bot.get_me()).username}?start=ref_{ref_code}`"
    ) + BRANDING

    await query.edit_message_text(text, parse_mode="Markdown")

# ---------- Referral System ----------
async def referrals(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ref_code = db.get_referral_code(user_id)
    ref_count = db.get_referral_stats(user_id)

    text = (
        f"👥 *Referral Program*\n\n"
        f"Share your referral link with friends. For each friend who joins and uses the bot, you get **{REFERRAL_BONUS_CYCLES} extra bombing cycles** (applied automatically to your next bomb).\n\n"
        f"🔗 Your link:\n"
        f"`https://t.me/{(await context.bot.get_me()).username}?start=ref_{ref_code}`\n\n"
        f"✅ Referrals: {ref_count}\n"
        f"🎁 Bonus cycles accumulated: {ref_count * REFERRAL_BONUS_CYCLES}"
    ) + BRANDING

    await query.edit_message_text(text, parse_mode="Markdown")

async def handle_referral(update, context):
    # Called when user starts with /start ref_<code>
    if context.args and context.args[0].startswith("ref_"):
        ref_code = context.args[0][4:]
        # Find user with that referral code
        conn = sqlite3.connect(db.DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id FROM premium WHERE referral_code = ?", (ref_code,))
        row = c.fetchone()
        conn.close()
        if row:
            referrer_id = row[0]
            user_id = update.effective_user.id
            if referrer_id != user_id:
                if db.add_referral(referrer_id, user_id):
                    await update.message.reply_text(f"✅ You were referred! The referrer will get {REFERRAL_BONUS_CYCLES} bonus cycles.")
                else:
                    await update.message.reply_text("You were already referred before.")
            else:
                await update.message.reply_text("You cannot refer yourself.")
        else:
            await update.message.reply_text("Invalid referral code.")
    # Continue with normal start
    await start(update, context)

# ---------- Premium Plans ----------
async def premium_plans(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📅 1 Month – ₹99", callback_data="premium_1m")],
        [InlineKeyboardButton("📅 3 Months – ₹249", callback_data="premium_3m")],
        [InlineKeyboardButton("📅 6 Months – ₹449", callback_data="premium_6m")],
        [InlineKeyboardButton("📅 1 Year – ₹799", callback_data="premium_12m")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ]
    await query.edit_message_text(
        "💎 *Premium Plans*\n\n"
        "• Unlimited bombing (no daily limit)\n"
        "• Longer durations (up to 24h)\n"
        "• Priority support\n"
        "• More features coming soon\n\n"
        "Select a plan to get payment details:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_premium_selection(update, context):
    query = update.callback_query
    data = query.data
    if data == "premium_1m":
        plan = "1 Month"
        days = 30
        price = 99
    elif data == "premium_3m":
        plan = "3 Months"
        days = 90
        price = 249
    elif data == "premium_6m":
        plan = "6 Months"
        days = 180
        price = 449
    elif data == "premium_12m":
        plan = "1 Year"
        days = 365
        price = 799
    else:
        return
    # Store plan details in context.user_data for later confirmation
    context.user_data["premium_plan"] = (plan, days, price)
    await query.edit_message_text(
        f"💰 *Plan Selected: {plan}*\n"
        f"💸 Price: ₹{price}\n\n"
        f"To activate, please send the payment to the following UPI ID:\n"
        f"`your-upi@okhdfcbank`\n\n"
        f"After payment, send the transaction ID using /confirm_payment <txn_id>.\n"
        f"We'll verify and activate your premium within 24 hours.\n\n"
        f"*Note:* This is a simulation for demo. In real bot, integrate with payment gateway.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="premium_plans")]])
    )

async def confirm_payment(update, context):
    # Simple manual confirmation; admin will verify and grant premium
    if not context.args:
        await update.message.reply_text("Usage: /confirm_payment <transaction_id>")
        return
    txn_id = context.args[0]
    # Notify admin
    await context.bot.send_message(OWNER_ID, f"💰 Payment confirmation from {update.effective_user.id}:\nTXID: {txn_id}")
    await update.message.reply_text("Payment recorded. Admin will verify and activate premium soon.")

# ---------- BOMBER (with referral bonus & cooldown) ----------
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

    # Cooldown check
    premium = db.is_premium(user_id)
    if not db.can_start_bomb(user_id, premium):
        await query.edit_message_text(
            f"❌ You have reached your daily limit ({FREE_DAILY_LIMIT} bombs) for free users.\n"
            f"Upgrade to premium for unlimited bombing!\n"
            f"Use '💎 Upgrade to Premium' in main menu."
        )
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
    premium = db.is_premium(user_id)
    # Check cooldown again (just in case)
    if not db.can_start_bomb(user_id, premium):
        msg = "❌ Daily limit reached. Upgrade to premium for unlimited bombing."
        if query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    # Log to channel
    if LOG_CHANNEL_ID:
        await context.bot.send_message(
            LOG_CHANNEL_ID,
            f"🔔 *New Bombing Request*\nUser: {user_id}\nTarget: +91{phone}\nDuration: {duration_sec} seconds\nTime: {datetime.now().isoformat()}",
            parse_mode="Markdown"
        )

    # Call start API
    start_result = await call_start_api(phone)
    start_text = format_json_human(start_result)
    msg = f"🔥 *Bombing Started!*\n\n{start_text}\n\nWill run for {duration_sec} seconds.\nUse /stop to cancel." + BRANDING
    if query:
        await query.edit_message_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

    # Apply referral bonus if any
    ref_bonus = db.get_referral_stats(user_id) * REFERRAL_BONUS_CYCLES
    if ref_bonus > 0:
        await context.bot.send_message(user_id, f"🎉 You have {ref_bonus} bonus cycles from referrals! They will be added to your session.")
        # We'll add bonus cycles to the current session (increase total cycles by ref_bonus)
        # We'll pass it to bombing loop
        context.user_data["bonus_cycles"] = ref_bonus
        # Reset referral bonus after using (or we can let it accumulate; for simplicity we'll use it once)
        # Optionally, we could mark that we used it. But for now, we'll just send message.

    # Update stats and increment bomb count
    db.update_stats(user_id, 0)  # cycles will be added later
    db.increment_bomb_count(user_id)

    # Start bombing loop
    task = asyncio.create_task(bombing_loop(user_id, phone, duration_sec, context))
    active_bombs[user_id] = task

async def bombing_loop(user_id, phone, duration_sec, context):
    end_time = datetime.now() + timedelta(seconds=duration_sec)
    iteration = 0
    # Bonus cycles from referrals
    bonus = context.user_data.get("bonus_cycles", 0)
    total_cycles = 0
    try:
        while datetime.now() < end_time:
            iteration += 1
            await asyncio.sleep(INTERVAL_SECONDS)
            if datetime.now() >= end_time:
                break
            result = await call_single_api(phone)
            text = f"📡 *Cycle #{iteration}*\n\n{format_json_human(result)}" + BRANDING
            await context.bot.send_message(user_id, text, parse_mode="Markdown")
            total_cycles += 1
        # Add bonus cycles (extra messages) after loop
        if bonus > 0:
            for i in range(bonus):
                result = await call_single_api(phone)
                text = f"🎁 *Bonus Cycle #{i+1} from referral*\n\n{format_json_human(result)}" + BRANDING
                await context.bot.send_message(user_id, text, parse_mode="Markdown")
                total_cycles += 1
                await asyncio.sleep(1)  # small delay

        stop_result = await call_stop_api(phone)
        await context.bot.send_message(
            user_id,
            f"🛑 *Bombing Stopped (duration ended)*\n\n{format_json_human(stop_result)}" + BRANDING,
            parse_mode="Markdown"
        )
        # Update total cycles in stats
        db.update_stats(user_id, total_cycles)
    except asyncio.CancelledError:
        stop_result = await call_stop_api(phone)
        await context.bot.send_message(
            user_id,
            f"🛑 *Bombing Stopped by user*\n\n{format_json_human(stop_result)}" + BRANDING,
            parse_mode="Markdown"
        )
        db.update_stats(user_id, total_cycles)
    finally:
        if user_id in active_bombs:
            del active_bombs[user_id]

# ---------- Scheduled Bombing ----------
async def schedule_bomb_start(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if db.is_banned(user_id):
        await query.edit_message_text("🚫 You are banned.")
        return
    if user_id in active_bombs:
        await query.edit_message_text("⚠️ You already have an active bombing session. Use /stop first.")
        return

    # Cooldown check for free users (schedule counts as a bomb)
    premium = db.is_premium(user_id)
    if not db.can_start_bomb(user_id, premium):
        await query.edit_message_text(
            f"❌ You have reached your daily limit ({FREE_DAILY_LIMIT} bombs) for free users.\n"
            f"Upgrade to premium for unlimited bombing!\n"
            f"Use '💎 Upgrade to Premium' in main menu."
        )
        return

    await query.edit_message_text("📞 Send me the *10-digit phone number* (only digits).\nType /cancel to abort.",
                                  parse_mode="Markdown")
    return SCHEDULE_DATE

async def schedule_get_phone(update, context):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ Invalid number. Please enter exactly 10 digits.")
        return SCHEDULE_DATE
    context.user_data["sched_phone"] = phone
    await update.message.reply_text("📅 Send the *date* in YYYY-MM-DD format (e.g., 2025-04-01):")
    return SCHEDULE_TIME

async def schedule_get_date(update, context):
    try:
        date_str = update.message.text.strip()
        scheduled_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if scheduled_date < datetime.now().date():
            await update.message.reply_text("❌ Date must be in the future.")
            return SCHEDULE_TIME
        context.user_data["sched_date"] = scheduled_date
        await update.message.reply_text("⏰ Send the *time* in HH:MM (24-hour format, e.g., 14:30):")
        return SCHEDULE_DATE  # wait for time
    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD.")
        return SCHEDULE_TIME

async def schedule_get_time(update, context):
    try:
        time_str = update.message.text.strip()
        hour, minute = map(int, time_str.split(':'))
        scheduled_time = datetime.combine(context.user_data["sched_date"], datetime.time(datetime(1,1,1, hour, minute)))
        if scheduled_time <= datetime.now():
            await update.message.reply_text("❌ The scheduled time must be in the future.")
            return SCHEDULE_DATE
        context.user_data["sched_datetime"] = scheduled_time
        # Ask for duration
        keyboard = [
            [InlineKeyboardButton("30 seconds", callback_data="sched_dur_30"),
             InlineKeyboardButton("1 minute", callback_data="sched_dur_60")],
            [InlineKeyboardButton("5 minutes", callback_data="sched_dur_300"),
             InlineKeyboardButton("10 minutes", callback_data="sched_dur_600")],
            [InlineKeyboardButton("30 minutes", callback_data="sched_dur_1800"),
             InlineKeyboardButton("1 hour", callback_data="sched_dur_3600")],
            [InlineKeyboardButton("2 hours", callback_data="sched_dur_7200"),
             InlineKeyboardButton("Custom", callback_data="sched_dur_custom")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        await update.message.reply_text(
            "⏱️ Choose duration:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SCHEDULE_DATE  # wait for duration
    except Exception:
        await update.message.reply_text("❌ Invalid time format. Use HH:MM (e.g., 14:30).")
        return SCHEDULE_DATE

async def schedule_duration(update, context):
    query = update.callback_query
    data = query.data
    if data == "cancel":
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    if data == "sched_dur_custom":
        await query.edit_message_text("Enter duration in seconds (e.g., 90 for 1.5 minutes):")
        return SCHEDULE_DATE  # custom duration input
    seconds = int(data.split("_")[2])
    context.user_data["sched_duration"] = seconds
    # Schedule the bomb
    user_id = update.effective_user.id
    phone = context.user_data["sched_phone"]
    scheduled_time = context.user_data["sched_datetime"]
    # Create a job that will run at scheduled_time
    job = context.application.job_queue.run_once(
        scheduled_bomb_task,
        when=scheduled_time,
        data={'user_id': user_id, 'phone': phone, 'duration': seconds, 'context': context}
    )
    context.user_data["sched_job"] = job
    # Log and confirm
    await query.edit_message_text(
        f"✅ Bomb scheduled for {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}.\n"
        f"Duration: {seconds} seconds.\n"
        f"You will be notified when it starts."
    )
    # Increment bomb count (since it's a scheduled bomb, we count it as used)
    db.increment_bomb_count(user_id)
    return ConversationHandler.END

async def scheduled_bomb_task(job):
    data = job.data
    user_id = data['user_id']
    phone = data['phone']
    duration_sec = data['duration']
    context = data['context']
    # Start bombing directly
    await context.bot.send_message(user_id, f"⏰ Your scheduled bomb is starting now!\nTarget: +91{phone}\nDuration: {duration_sec} seconds")
    # Call start API
    start_result = await call_start_api(phone)
    start_text = format_json_human(start_result)
    await context.bot.send_message(user_id, f"🔥 *Bombing Started!*\n\n{start_text}\n\nWill run for {duration_sec} seconds.\nUse /stop to cancel." + BRANDING, parse_mode="Markdown")
    # Run bombing loop
    task = asyncio.create_task(bombing_loop(user_id, phone, duration_sec, context))
    active_bombs[user_id] = task

# ---------- ADMIN PANEL (Extended) ----------
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
        [InlineKeyboardButton("👑 Grant Premium", callback_data="admin_grant_premium")],
        [InlineKeyboardButton("👑 Revoke Premium", callback_data="admin_revoke_premium")],
        [InlineKeyboardButton("📊 User Stats", callback_data="admin_user_stats")],
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
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        try:
            shutil.copy2(db.DB_FILE, backup_name)
            with open(backup_name, 'rb') as f:
                await context.bot.send_document(update.effective_chat.id, f, caption="📀 Database backup")
            os.remove(backup_name)
            await query.edit_message_text("Backup sent. Returning to admin panel.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]]))
        except Exception as e:
            await query.edit_message_text(f"Backup failed: {e}")
        return

    if data in ["admin_addadmin", "admin_removeadmin"] and user_id == OWNER_ID:
        context.user_data["admin_action"] = data
        await query.edit_message_text("Send the user ID:")
        return ADMIN_BAN

    if data == "admin_grant_premium":
        context.user_data["admin_action"] = "grant_premium"
        await query.edit_message_text("Send the user ID to grant premium:")
        return ADMIN_PREMIUM_USER
    if data == "admin_revoke_premium":
        context.user_data["admin_action"] = "revoke_premium"
        await query.edit_message_text("Send the user ID to revoke premium:")
        return ADMIN_PREMIUM_USER
    if data == "admin_user_stats":
        context.user_data["admin_action"] = "user_stats"
        await query.edit_message_text("Send the user ID to view stats:")
        return ADMIN_PREMIUM_USER

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

async def admin_premium_user(update, context):
    action = context.user_data.get("admin_action")
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("Invalid user ID.")
        return ADMIN_PREMIUM_USER

    if action == "grant_premium":
        context.user_data["premium_target"] = target_id
        await update.message.reply_text("Enter number of days to grant (e.g., 30):")
        return ADMIN_PREMIUM_DAYS
    elif action == "revoke_premium":
        db.remove_premium(target_id)
        await update.message.reply_text(f"Premium revoked for user {target_id}.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    elif action == "user_stats":
        total_bombs, total_cycles = db.get_stats(target_id)
        premium = db.is_premium(target_id)
        expiry = db.get_premium_expiry(target_id)
        ref = db.get_referral_stats(target_id)
        text = (
            f"📊 *Stats for user {target_id}*\n"
            f"Premium: {'Yes' if premium else 'No'}\n"
            f"Expiry: {expiry.strftime('%Y-%m-%d') if expiry else 'N/A'}\n"
            f"Total Bombs: {total_bombs}\n"
            f"Total Cycles: {total_cycles}\n"
            f"Referrals: {ref}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    else:
        return ConversationHandler.END

async def admin_premium_days(update, context):
    try:
        days = int(update.message.text.strip())
        target = context.user_data["premium_target"]
        if days <= 0:
            raise ValueError
        # Extend premium (if user has premium, extend; else create)
        if db.is_premium(target):
            db.extend_premium(target, days)
        else:
            db.create_premium(target, days)
        await update.message.reply_text(f"Premium granted for {days} days to user {target}.")
        await admin_panel_after_action(update, context)
        return ConversationHandler.END
    except:
        await update.message.reply_text("Invalid number of days.")
        return ADMIN_PREMIUM_DAYS

# ---------- General Callback Handler ----------
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
    if data == "schedule_bomb":
        await schedule_bomb_start(update, context)
        return
    if data == "profile":
        await profile(update, context)
        return
    if data == "referrals":
        await referrals(update, context)
        return
    if data == "premium_plans":
        await premium_plans(update, context)
        return
    if data.startswith("premium_") and data != "premium_plans":
        await handle_premium_selection(update, context)
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

    # If none matched, maybe admin action? But they have separate conversation.
    # Default: just ignore.
    await query.answer("Invalid action", show_alert=False)

# ---------- Standard Info/Help ----------
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
        "Premium features:\n"
        "• Unlimited bombing (no daily limit)\n"
        "• Schedule bombs for future\n"
        "• Longer durations\n\n"
        "Admin panel has all management tools." + BRANDING,
        parse_mode="Markdown"
    )

# ---------- Scheduled Backup ----------
async def scheduled_backup(context: ContextTypes.DEFAULT_TYPE):
    """Send daily backup to owner."""
    try:
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(db.DB_FILE, backup_name)
        with open(backup_name, 'rb') as f:
            await context.bot.send_document(OWNER_ID, f, caption=f"📀 Daily backup {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        os.remove(backup_name)
    except Exception as e:
        await context.bot.send_message(OWNER_ID, f"Daily backup failed: {e}")

# ---------- MAIN ----------
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

    # Scheduled bombing conversation
    sched_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(schedule_bomb_start, pattern="^schedule_bomb$")],
        states={
            SCHEDULE_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_get_phone),
                CallbackQueryHandler(schedule_duration, pattern="^sched_dur_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_get_date),
            ],
            SCHEDULE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_get_time),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("Cancelled."))],
        per_message=False
    )
    app.add_handler(sched_conv)

    # Admin conversations
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_action, pattern="^admin_")],
        states={
            ADMIN_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_get_user_id)],
            ADMIN_DM_MSG: [MessageHandler(filters.ALL, admin_get_dm_message)],
            ADMIN_BROADCAST: [MessageHandler(filters.ALL, admin_broadcast_message)],
            ADMIN_BULKDM: [MessageHandler(filters.ALL, admin_bulkdm_message)],
            ADMIN_PREMIUM_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_premium_user)],
            ADMIN_PREMIUM_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_premium_days)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("Cancelled."))],
        per_message=False
    )
    app.add_handler(admin_conv)

    # Regular commands
    app.add_handler(CommandHandler("start", handle_referral))  # handles referral and then start
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("confirm_payment", confirm_payment))

    # General callback handler
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^(?!admin_|bomber$|dur_|sched_dur_|premium_).*"))

    # Scheduled backup
    if app.job_queue:
        app.job_queue.run_daily(scheduled_backup, time=datetime.strptime("00:00", "%H:%M").time())
        print("Scheduled backup enabled (daily at 00:00 UTC).")
    else:
        print("Warning: JobQueue not available. Scheduled backup disabled.")

    print("Bot started...")
    app.run_polling()

# Helper functions needed for admin conversation (unchanged)
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
        conn = sqlite3.connect(db.DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
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
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"Broadcast sent to {sent}/{len(users)} users.")
    except Exception as e:
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
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"Bulk DM sent to {sent}/{len(users)} users.")
    except Exception as e:
        await update.message.reply_text(f"Bulk DM failed: {e}")
    await admin_panel_after_action(update, context)
    return ConversationHandler.END

async def admin_panel_after_action(update, context):
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")]]
    await update.message.reply_text("Action completed.", reply_markup=InlineKeyboardMarkup(keyboard))

async def stop(update, context):
    user_id = update.effective_user.id
    if user_id in active_bombs:
        active_bombs[user_id].cancel()
        await update.message.reply_text("🛑 Stopping bombing...")
    else:
        await update.message.reply_text("No active bombing session.")

if __name__ == "__main__":
    main()
