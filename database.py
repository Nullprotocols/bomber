import sqlite3
from datetime import datetime, timedelta

DB_FILE = "bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Existing tables
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            banned INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    """)
    # New tables for pro version
    c.execute("""
        CREATE TABLE IF NOT EXISTS premium (
            user_id INTEGER PRIMARY KEY,
            expiry_date TEXT,
            referral_code TEXT UNIQUE,
            referral_count INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER,
            date TEXT,
            PRIMARY KEY (referrer_id, referred_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_bombs INTEGER DEFAULT 0,
            total_cycles INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS cooldown (
            user_id INTEGER PRIMARY KEY,
            bomb_count_today INTEGER DEFAULT 0,
            last_bomb_date TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
              (user_id, username, first_name))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def ban_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def is_admin(user_id, owner_id):
    if user_id == owner_id:
        return True
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_admin(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

def get_admins():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins")
    admins = [row[0] for row in c.fetchall()]
    conn.close()
    return admins

# ---------- Premium functions ----------
def generate_referral_code(user_id):
    import base64
    code = base64.urlsafe_b64encode(str(user_id).encode()).decode().rstrip('=')
    return code

def create_premium(user_id, days=30, referral_code=None):
    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    if not referral_code:
        referral_code = generate_referral_code(user_id)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO premium (user_id, expiry_date, referral_code, referral_count) VALUES (?, ?, ?, COALESCE((SELECT referral_count FROM premium WHERE user_id=?), 0))",
              (user_id, expiry, referral_code, user_id))
    conn.commit()
    conn.close()

def is_premium(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM premium WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        expiry = datetime.fromisoformat(row[0])
        return expiry > datetime.now()
    return False

def get_premium_expiry(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM premium WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row[0])
    return None

def extend_premium(user_id, days=30):
    current = get_premium_expiry(user_id)
    if current and current > datetime.now():
        new_expiry = current + timedelta(days=days)
    else:
        new_expiry = datetime.now() + timedelta(days=days)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE premium SET expiry_date = ? WHERE user_id = ?", (new_expiry.isoformat(), user_id))
    conn.commit()
    conn.close()

def remove_premium(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM premium WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_referral_code(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT referral_code FROM premium WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def add_referral(referrer_id, referred_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Check if already referred
    c.execute("SELECT 1 FROM referrals WHERE referrer_id=? AND referred_id=?", (referrer_id, referred_id))
    if c.fetchone():
        conn.close()
        return False
    # Add referral record
    c.execute("INSERT INTO referrals (referrer_id, referred_id, date) VALUES (?, ?, ?)",
              (referrer_id, referred_id, datetime.now().isoformat()))
    # Increment referrer's referral count
    c.execute("UPDATE premium SET referral_count = referral_count + 1 WHERE user_id = ?", (referrer_id,))
    conn.commit()
    conn.close()
    return True

def get_referral_stats(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT referral_count FROM premium WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ---------- User Stats ----------
def update_stats(user_id, cycles):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO user_stats (user_id, total_bombs, total_cycles) VALUES (?, 1, ?) "
              "ON CONFLICT(user_id) DO UPDATE SET total_bombs = total_bombs + 1, total_cycles = total_cycles + ?",
              (user_id, cycles, cycles))
    conn.commit()
    conn.close()

def get_stats(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT total_bombs, total_cycles FROM user_stats WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return 0, 0

# ---------- Cooldown for free users ----------
def can_start_bomb(user_id, is_premium):
    if is_premium:
        return True
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    c.execute("SELECT bomb_count_today, last_bomb_date FROM cooldown WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return True
    last_date = row[1] if row[1] else ""
    if last_date != today:
        # Reset counter
        c.execute("UPDATE cooldown SET bomb_count_today = 0, last_bomb_date = ? WHERE user_id = ?", (today, user_id))
        conn.commit()
        conn.close()
        return True
    if row[0] >= 3:  # 3 bombs per day for free users
        conn.close()
        return False
    conn.close()
    return True

def increment_bomb_count(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    c.execute("INSERT INTO cooldown (user_id, bomb_count_today, last_bomb_date) VALUES (?, 1, ?) "
              "ON CONFLICT(user_id) DO UPDATE SET bomb_count_today = bomb_count_today + 1, last_bomb_date = ?",
              (user_id, today, today))
    conn.commit()
    conn.close()
