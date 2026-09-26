import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote_plus, urlencode
from io import BytesIO

import qrcode

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from dotenv import load_dotenv
from telegram import (
    Update,
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton as _TelegramInlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# =============================================================================
# CONFIG
# =============================================================================
DB_FILE = Path(os.getenv("DB_FILE", "database.json"))
IST = pytz.timezone("Asia/Kolkata")

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OWNER_IDS = [
    int(x.strip()) for x in os.getenv("OWNER_IDS", "8853678390").split(",")
    if x.strip().isdigit()
]

# These are defaults. You can change them from Admin -> Settings.
DEFAULT_CONFIG = {
    "upi_id": os.getenv("UPI_ID", "sandeepshoww@oksbi"),
    "upi_name": os.getenv("UPI_NAME", "nrzravi"),
    "admin_contact": os.getenv("ADMIN_CONTACT", "@nrzravi"),
    "payment_qr_file_id": os.getenv("PAYMENT_QR_FILE_ID", ""),
    "how_to_pay_url": os.getenv("HOW_TO_PAY_URL", ""),
    "how_to_pay_text": os.getenv("HOW_TO_PAY_TEXT", "How to Pay"),
    "verify_reward": float(os.getenv("VERIFY_REWARD", "0.5")),
    "referral_reward": float(os.getenv("REFERRAL_REWARD", "0.5")),
    "daily_reminder_hour": 4,
    "daily_reminder_minute": 0,
    "plans": {
        "220": {
            "id": "220",
            "name": "220 Likes / Day",
            "active": True,
            "packages": {
                "220p1": {"id": "220p1", "name": "❤️ 15 Coins — 1 Day » 200 Likes", "coins": 15, "days": 1, "active": True},
                "220p2": {"id": "220p2", "name": "❤️ 90 Coins — 15 Day » 3300 Likes", "coins": 90, "days": 15, "active": True},
                "220p3": {"id": "220p3", "name": "💎 180 Coins — 30 Day » 6600 Likes", "coins": 180, "days": 30, "active": True},
                "220p4": {"id": "220p4", "name": "👑 350 Coins — 60 Day » 13200 Likes", "coins": 350, "days": 60, "active": True},
                "220p5": {"id": "220p5", "name": "❤️ 740 Coins — 120 Day » 26400 Likes", "coins": 740, "days": 120, "active": True},
                "220p6": {"id": "220p6", "name": "❤️ 1400 Coins — 240 Day » 52800 Likes", "coins": 1400, "days": 240, "active": True}
            },
        },
        "500": {
            "id": "500",
            "name": "500+ Likes / Day",
            "active": True,
            "packages": {
                "500p1": {"id": "500p1", "name": "⚡ 45 Coins — 1 Day » 500 Likes", "coins": 45, "days": 1, "active": True},
                "500p2": {"id": "500p2", "name": "💥 150 Coins — 7 Day » 3500 Likes", "coins": 150, "days": 7, "active": True},
                "500p3": {"id": "500p3", "name": "💥 240 Coins — 15 Day » 7500 Likes", "coins": 240, "days": 15, "active": True},
                "500p4": {"id": "500p4", "name": "🔥 500 Coins — 30 Day » 15000 Likes", "coins": 500, "days": 30, "active": True},
                "500p5": {"id": "500p5", "name": "👑 1000 Coins — 60 Day » 30000 Likes", "coins": 1000, "days": 60, "active": True}
            },
        },
    },
    "coin_pricing": [
        {"id": "p50", "amount": 50, "coins": 55, "active": True},
        {"id": "p100", "amount": 100, "coins": 110, "active": True},
        {"id": "p200", "amount": 200, "coins": 220, "active": True},
        {"id": "p500", "amount": 500, "coins": 575, "active": True},
        {"id": "p1000", "amount": 1000, "coins": 1200, "active": True},
    ],
}

REGIONS = [
    ("🇮🇳 India", "IND"),
    ("🇳🇵 Nepal", "NP"),
    ("🇧🇩 Bangladesh", "BD"),
    ("🇵🇰 Pakistan", "PK"),
    ("🇸🇬 Singapore", "SG"),
    ("🇮🇩 Indonesia", "ID"),
    ("🇧🇷 Brazil", "BR"),
    ("🇺🇸 USA", "US"),
    ("🌍 Middle East", "ME"),
    ("🇪🇺 Europe", "EU"),
    ("🇻🇳 Vietnam", "VN"),
    ("🇹🇭 Thailand", "TH"),
    ("🇲🇾 Malaysia", "MY"),
    ("🇵🇭 Philippines", "PH"),
    ("🌎 CIS Region", "CIS"),
    ("🌎 Latin America", "LATAM"),
]

REGION_NAMES = dict(REGIONS)


def now_ist():
    return datetime.now(IST)


def iso_now():
    return now_ist().strftime("%Y-%m-%d %H:%M:%S")


def is_owner(user_id: int) -> bool:
    return int(user_id) in OWNER_IDS


def new_db():
    return {
        "config": DEFAULT_CONFIG,
        "users": {},
        "autolikes": [],
        "autolike_orders": [],
        "coin_orders": [],
        "redeem_codes": {},
        "verify_tasks": [],
        "verify_redemptions": {},
        "referrals": {},
        "stats": {"total_bought_coins": 0, "total_earned_coins": 0},
    }


def deep_merge(default, existing):
    if isinstance(default, dict):
        out = dict(default)
        if isinstance(existing, dict):
            for k, v in existing.items():
                if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                    out[k] = deep_merge(out[k], v)
                else:
                    out[k] = v
        return out
    return existing if existing is not None else default


def load_db():
    if not DB_FILE.exists():
        return new_db()
    try:
        data = json.loads(DB_FILE.read_text(encoding="utf-8"))
        # Keep old project data usable.
        if "users" not in data:
            data["users"] = {}
        if "autolikes" not in data:
            data["autolikes"] = []
        data = deep_merge(new_db(), data)
        return data
    except (json.JSONDecodeError, OSError):
        return new_db()


db = load_db()
# Upgrade legacy payment defaults from the earlier sample account.
if db.get("config", {}).get("upi_id") == "s.ta.r.x.sharma@fam":
    db["config"]["upi_id"] = "sandeepshoww@oksbi"
if db.get("config", {}).get("upi_name") == "MANISH SHARMA":
    db["config"]["upi_name"] = "nrzravi"


def normalize_catalog_config():
    """Upgrade old 220/500 package data into the new plan/package structure."""
    cfg = db.setdefault("config", {})

    plans = cfg.get("plans")
    if not isinstance(plans, dict) or not plans:
        plans = {}
        legacy = cfg.get("packages", {})
        for key, item in legacy.items():
            key = str(key)
            title = str(item.get("title", key))
            plans[key] = {
                "id": key,
                "name": title,
                "active": True,
                "packages": {
                    f"{key}pkg": {
                        "id": f"{key}pkg",
                        "name": title,
                        "coins": coins(item.get("coins", 0)),
                        "days": int(item.get("days", 1)),
                        "active": True,
                    }
                },
            }
        cfg["plans"] = plans

    # Migrate the old fixed 220/500 package settings once if they exist.
    legacy = cfg.get("packages")
    if isinstance(legacy, dict) and not cfg.get("_plans_migrated", False):
        for key, old_item in legacy.items():
            plan = cfg.get("plans", {}).get(str(key))
            if not plan:
                continue
            pkgs = plan.setdefault("packages", {})
            first = next(iter(pkgs.values()), None)
            if first:
                first["coins"] = coins(old_item.get("coins", first.get("coins", 0)))
                try: first["days"] = int(old_item.get("days", first.get("days", 1)))
                except (TypeError, ValueError): pass
                if old_item.get("title"):
                    # Keep the old title as the first package button when it was customized.
                    first["name"] = str(old_item["title"])
        cfg["_plans_migrated"] = True

    # Normalize plans/packages if a previous version stored them as lists.
    if isinstance(cfg.get("plans"), list):
        cfg["plans"] = {str(x.get("id") or uuid.uuid4().hex[:8]): x for x in cfg["plans"]}
    for pid, plan in list(cfg.get("plans", {}).items()):
        plan["id"] = str(plan.get("id") or pid)
        plan.setdefault("name", str(pid))
        plan.setdefault("active", True)
        pkgs = plan.get("packages", {})
        if isinstance(pkgs, list):
            pkgs = {str(x.get("id") or uuid.uuid4().hex[:8]): x for x in pkgs}
        plan["packages"] = pkgs if isinstance(pkgs, dict) else {}
        for pkgid, pkg in list(plan["packages"].items()):
            pkg["id"] = str(pkg.get("id") or pkgid)
            pkg.setdefault("name", "AutoLike Package")
            pkg["coins"] = coins(pkg.get("coins", 0))
            try:
                pkg["days"] = int(pkg.get("days", 1))
            except (TypeError, ValueError):
                pkg["days"] = 1
            pkg.setdefault("active", True)

    pricing = cfg.get("coin_pricing")
    if not isinstance(pricing, list) or not pricing:
        cfg["coin_pricing"] = [
            {"id": "p50", "amount": 50, "coins": 55, "active": True},
            {"id": "p100", "amount": 100, "coins": 110, "active": True},
            {"id": "p200", "amount": 200, "coins": 220, "active": True},
            {"id": "p500", "amount": 500, "coins": 575, "active": True},
            {"id": "p1000", "amount": 1000, "coins": 1200, "active": True},
        ]
    for item in cfg["coin_pricing"]:
        item.setdefault("id", uuid.uuid4().hex[:8])
        try: item["amount"] = int(item.get("amount", 0))
        except (TypeError, ValueError): item["amount"] = 0
        item["coins"] = coins(item.get("coins", 0))
        item.setdefault("active", True)


def InlineKeyboardButton(text, *args, **kwargs):
    """Styled inline buttons, compatible with PTB 22.5 / Python 3.9.

    PTB 22.7 added a dedicated ``style=`` constructor argument, but this
    hosting environment uses Python 3.9 and therefore can install only up to
    PTB 22.5. PTB 22.5 already supports ``api_kwargs`` and includes those
    fields in the outgoing Bot API JSON, so we pass the Bot API ``style``
    field through ``api_kwargs`` instead.
    The main 7-button ReplyKeyboard remains unchanged.
    """
    if "style" not in kwargs and "api_kwargs" not in kwargs:
        low = str(text).lower()
        if any(x in low for x in ("❌", "delete", "reject", "remove", "danger", "inactive")):
            button_style = "danger"
        elif any(x in low for x in ("✅", "approve", "confirm", "add ", "save", "active")):
            button_style = "success"
        else:
            button_style = "primary"
        kwargs["api_kwargs"] = {"style": button_style}
    return _TelegramInlineKeyboardButton(text, *args, **kwargs)


def save_db():
    tmp = DB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DB_FILE)


def user_record(tg_user):
    uid = str(tg_user.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "id": tg_user.id,
            "name": tg_user.full_name or tg_user.first_name or "User",
            "username": tg_user.username or "",
            "coins": 0.0,
            "total_bought": 0.0,
            "total_earned": 0.0,
            "joined_at": iso_now(),
            "referred_by": None,
        }
    else:
        db["users"][uid]["name"] = tg_user.full_name or tg_user.first_name or db["users"][uid].get("name", "User")
        db["users"][uid]["username"] = tg_user.username or db["users"][uid].get("username", "")
    return db["users"][uid]


def coins(v):
    return round(float(v), 2)


def fmt_coins(v):
    n = coins(v)
    return f"{n:.2f}".rstrip("0").rstrip(".")


normalize_catalog_config()
save_db()


def valid_uid(text):
    return bool(re.fullmatch(r"\d{6,15}", text.strip()))


def valid_utr(text):
    text = text.strip()
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{6,40}", text))


def main_kb(user_id=None):
    # Main user menu is a Telegram reply keyboard, so it stays at the bottom
    # of the chat just like the original shop-bot screenshot. Admin controls
    # are intentionally NOT included here.
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🛒 Buy Autolike"), KeyboardButton("📁 My Autolikes")],
            [KeyboardButton("🎟 Redeem Code"), KeyboardButton("💰 Buy Coins")],
            [KeyboardButton("💳 My Balance"), KeyboardButton("👥 Earn Coins")],
            [KeyboardButton("❓ Help & Support")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option…",
    )


def back_menu_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu_back")]])


def cancel_kb(callback="cancel_flow"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=callback)]])


def get_plans(include_inactive=False):
    plans = list(db["config"].get("plans", {}).values())
    return plans if include_inactive else [p for p in plans if p.get("active", True)]


def find_plan(plan_id):
    return db["config"].get("plans", {}).get(str(plan_id))


def find_package(plan, package_id):
    if not plan:
        return None
    return plan.get("packages", {}).get(str(package_id))


def package_kb():
    plans = get_plans()
    rows = [[InlineKeyboardButton(str(p.get("name", "Plan")), callback_data=f"auto_plan_{p['id']}")] for p in plans]
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_flow")])
    return InlineKeyboardMarkup(rows)


def plan_packages_kb(plan):
    rows = []
    for pkg in plan.get("packages", {}).values():
        if pkg.get("active", True):
            rows.append([InlineKeyboardButton(str(pkg.get("name", "Package")), callback_data=f"auto_pkg_{plan['id']}_{pkg['id']}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu_buy_auto")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_flow")])
    return InlineKeyboardMarkup(rows)

def region_kb(prefix="auto_region"):
    rows = []
    for i in range(0, len(REGIONS), 2):
        row = []
        for label, code in REGIONS[i:i+2]:
            row.append(InlineKeyboardButton(label, callback_data=f"{prefix}_{code}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu_buy_auto")])
    return InlineKeyboardMarkup(rows)


def summary_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm Order", callback_data="auto_confirm"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_flow")],
    ])


def payment_packages_kb():
    rows = []
    for item in db["config"].get("coin_pricing", []):
        if item.get("active", True):
            rows.append([InlineKeyboardButton(
                f"₹{item['amount']} → {fmt_coins(item['coins'])} coins",
                callback_data=f"coin_pkg_{item['id']}"
            )])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_flow")])
    return InlineKeyboardMarkup(rows)

def payment_uri(amount):
    cfg = db["config"]
    # Standard UPI deep-link. The amount is fixed to the selected package.
    return "upi://pay?" + urlencode({
        "pa": cfg.get("upi_id", "sandeepshoww@oksbi"),
        "pn": cfg.get("upi_name", "nrzravi"),
        "am": f"{float(amount):.2f}",
        "cu": "INR",
    })


def make_payment_qr(amount):
    qr = qrcode.QRCode(version=None, box_size=9, border=4)
    qr.add_data(payment_uri(amount))
    qr.make(fit=True)
    img = qr.make_image()
    bio = BytesIO()
    bio.name = "upi_payment_qr.png"
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio


def payment_text(amount, coin_amount):
    cfg = db["config"]
    upi = cfg.get("upi_id", "sandeepshoww@oksbi")
    name = cfg.get("upi_name", "nrzravi")
    return (
        "🇮🇳 <b>UPI Payment</b>\n\n"
        f"Coins: <b>{fmt_coins(coin_amount)}</b>\n"
        f"Amount: <b>₹{amount}</b>\n\n"
        f"📲 UPI ID: <code>{upi}</code>\n"
        f"👤 Name: <b>{name}</b>\n\n"
        "⚠️ Pay the exact amount using the QR above or UPI ID and click <b>I Have Paid</b>."
    )


def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Pending AutoLike Orders", callback_data="admin_auto_pending")],
        [InlineKeyboardButton("💳 Pending Coin Payments", callback_data="admin_coin_pending")],
        [InlineKeyboardButton("👤 Manage Users", callback_data="admin_users")],
        [InlineKeyboardButton("🎟 Redeem Codes", callback_data="admin_codes")],
        [InlineKeyboardButton("🔗 Verify & Earn", callback_data="admin_verify")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("📋 Active AutoLikes", callback_data="admin_active")],
        [InlineKeyboardButton("⬅️ User Menu", callback_data="menu_back")],
    ])


def admin_back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")]])


def admin_order_actions(order_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"admin_auto_approve_{order_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"admin_auto_reject_{order_id}")],
        [InlineKeyboardButton("⚙️ Manage", callback_data=f"admin_auto_manage_{order_id}")],
    ])


def admin_payment_actions(order_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"admin_coin_approve_{order_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"admin_coin_reject_{order_id}")],
        [InlineKeyboardButton("⚙️ Manage", callback_data=f"admin_coin_manage_{order_id}")],
    ])


def contact_admin_kb():
    username = db["config"].get("admin_contact", "@nrzravi").lstrip("@")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Contact Admin", url=f"https://t.me/{username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu_back")],
    ])


def referral_kb(share_url):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={quote_plus(share_url)}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu_earn")],
    ])


def how_to_pay_kb():
    url = db["config"].get("how_to_pay_url", "")
    if url:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📹 How to Pay", url=url)],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu_buy_coins")],
        ])
    return back_menu_kb()


async def safe_delete(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def edit_or_reply(query, text, markup=None):
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await query.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def send_admins(context, text, markup=None, photo=None):
    for admin_id in OWNER_IDS:
        try:
            if photo:
                await context.bot.send_photo(admin_id, photo=photo, caption=text, reply_markup=markup, parse_mode="HTML")
            else:
                await context.bot.send_message(admin_id, text=text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            print("Admin notification error:", e)


async def notify_user(context, user_id, text, markup=None):
    try:
        await context.bot.send_message(user_id, text=text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        print("User notification error:", e)


# =============================================================================
# /start + referral
# =============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = user_record(update.effective_user)
    payload = context.args[0] if context.args else ""

    # Referral is credited only when a genuinely new user starts with another user's link.
    if payload.startswith("ref_") and not u.get("referred_by"):
        try:
            referrer_id = int(payload[4:])
        except ValueError:
            referrer_id = 0
        if referrer_id and referrer_id != update.effective_user.id and str(referrer_id) in db["users"]:
            u["referred_by"] = str(referrer_id)
            ref = db["users"][str(referrer_id)]
            reward = coins(db["config"].get("referral_reward", 0.5))
            ref["coins"] = coins(ref.get("coins", 0) + reward)
            ref["total_earned"] = coins(ref.get("total_earned", 0) + reward)
            db["stats"]["total_earned_coins"] = coins(db["stats"].get("total_earned_coins", 0) + reward)
            db["referrals"].setdefault(str(referrer_id), []).append(str(update.effective_user.id))
            save_db()
            await notify_user(context, referrer_id,
                              f"👥 <b>Referral Earned</b>\n\nYou earned <b>{fmt_coins(reward)} coins</b> from a new referral.")
    save_db()
    await send_welcome_message(update.message, update.effective_user.id)


# =============================================================================
# User flows
# =============================================================================

MENU_TEXT_TO_CALLBACK = {
    "🛒 Buy Autolike": "menu_buy_auto",
    "📁 My Autolikes": "menu_my_auto",
    "🎟 Redeem Code": "menu_redeem",
    "💰 Buy Coins": "menu_buy_coins",
    "💳 My Balance": "menu_balance",
    "👥 Earn Coins": "menu_earn",
    "❓ Help & Support": "menu_help",
}


async def send_welcome_message(message, user_id):
    text = (
        f"👋 <b>Welcome, {message.from_user.first_name}!</b>\n\n"
        "🛍 <b>FF Autolikes Shop Bot</b>\n\n"
        "Choose an option below:"
    )
    await message.reply_text(text, reply_markup=main_kb(user_id), parse_mode="HTML")


async def finish_payment_wait_message(context, order, text, markup=None):
    chat_id = order.get("verification_chat_id")
    message_id = order.get("verification_message_id")
    if not chat_id or not message_id:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text,
            reply_markup=markup, parse_mode="HTML"
        )
    except Exception as e:
        print("Payment status message edit error:", e)


VERIFY_MESSAGES = [
    ("⏳ <b>Auto-verifying payment details...</b>", 5),
    ("🔄 <b>Processing payment verification...</b>", 5),
    ("🔎 <b>Verification in process...</b>", 3),
    ("⏱️ <b>Checking transaction details...</b>", 8),
    ("⌛ <b>It may take up to 10 minutes...</b>", 5),
    ("🔐 <b>Securely checking UTR and payment...</b>", 8),
    ("📡 <b>Waiting for payment confirmation...</b>", 5),
    ("🧾 <b>Cross-checking transaction record...</b>", 8),
]


async def payment_verification_loop(context, order_id):
    """Keep the payment message in a changing verification state for 10 minutes.
    Admin approval/rejection ends the loop immediately. No payment API is called.
    """
    started = asyncio.get_running_loop().time()
    index = 0
    total_seconds = 10 * 60
    while asyncio.get_running_loop().time() - started < total_seconds:
        order = next((x for x in db["coin_orders"] if x.get("id") == order_id), None)
        if not order or order.get("status") != "verifying":
            return
        message, delay = VERIFY_MESSAGES[index % len(VERIFY_MESSAGES)]
        await finish_payment_wait_message(context, order, message)
        remaining = total_seconds - (asyncio.get_running_loop().time() - started)
        await asyncio.sleep(min(delay, max(0.1, remaining)))
        index += 1

    order = next((x for x in db["coin_orders"] if x.get("id") == order_id), None)
    if not order or order.get("status") != "verifying":
        return
    order["status"] = "manual_review"
    order["auto_verify_failed_at"] = iso_now()
    save_db()
    await finish_payment_wait_message(
        context, order,
        "⚠️ <b>Auto-verify failed.</b>\n\nPlease contact admin for manual verification.",
        contact_admin_kb(),
    )

async def show_buy_auto(query, context):
    context.user_data.clear()
    context.user_data["flow"] = "auto"
    await edit_or_reply(query,
        "🛒 <b>Select Autolike Plan</b>\n\nChoose your package type:", package_kb())


async def show_buy_coins(query, context):
    context.user_data.clear()
    context.user_data["flow"] = "coins"
    await edit_or_reply(query,
        "💰 <b>Select UPI Package</b>\n\nChoose the amount you want to pay:",
        payment_packages_kb())


async def show_balance(query):
    u = db["users"].get(str(query.from_user.id), {})
    text = (
        "💳 <b>My Balance</b>\n\n"
        f"Current balance: <b>{fmt_coins(u.get('coins', 0))} coins</b>\n"
        f"Total bought: <b>{fmt_coins(u.get('total_bought', 0))} coins</b>\n"
        f"Total earned: <b>{fmt_coins(u.get('total_earned', 0))} coins</b>"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Coins", callback_data="menu_buy_coins")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu_back")],
    ])
    await edit_or_reply(query, text, markup)


async def show_my_autolikes(query):
    uid = str(query.from_user.id)
    orders = [o for o in db["autolike_orders"] if str(o.get("user_id")) == uid and o.get("status") == "approved"]
    if not orders:
        text = "📁 <b>My Autolikes</b>\n\nNo orders show here yet.\n\nYour accepted AutoLike orders will appear here."
    else:
        lines = []
        for i, o in enumerate(reversed(orders[-20:]), 1):
            lines.append(
                f"<b>{i}. {o['package_title']}</b>\n"
                f"UID: <code>{o['uid']}</code>\n"
                f"Region: {REGION_NAMES.get(o['region'], o['region'])}\n"
                f"Days: {o['days']}\n"
                f"Status: {o['status'].title()}\n"
                f"Accepted: {o.get('approved_at', 'N/A')}"
            )
        text = "📁 <b>My Autolikes</b>\n\n" + "\n\n".join(lines)
    await edit_or_reply(query, text, back_menu_kb())


async def show_earn(query):
    await edit_or_reply(query,
        "👥 <b>Earn Coins</b>\n\nChoose a method:",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Verify & Earn", callback_data="earn_verify")],
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="earn_ref")],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu_back")],
        ]))


async def show_verify_tasks(query):
    tasks = [t for t in db["verify_tasks"] if t.get("active", True)]
    if not tasks:
        await edit_or_reply(query, "🔗 <b>Verify & Earn</b>\n\nNo active verification tasks right now.", back_menu_kb())
        return
    rows = []
    text = "🔗 <b>Verify & Earn</b>\n\nComplete the links, then enter the code you receive. Each active code can be redeemed once per user.\n\n"
    for t in tasks:
        text += f"• <b>{t.get('title','Verification')}</b> — +{fmt_coins(t.get('reward',0.5))} coins\n"
        rows.append([InlineKeyboardButton(f"🔗 {t.get('title','Open Link')}", url=t["url"])])
    rows.append([InlineKeyboardButton("🔑 Enter Code", callback_data="verify_enter_code")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu_earn")])
    await edit_or_reply(query, text, InlineKeyboardMarkup(rows))


async def show_referral(query, context):
    me = query.from_user
    bot_me = await context.bot.get_me()
    me_url = f"https://t.me/{bot_me.username}?start=ref_{me.id}"
    refs = db["referrals"].get(str(me.id), [])
    reward = db["config"].get("referral_reward", 0.5)
    text = (
        "👥 <b>Referral Program</b>\n\n"
        f"Earn <b>{fmt_coins(reward)} coins</b> per successful referral!\n\n"
        f"🔗 <b>Your link:</b>\n<code>{me_url}</code>\n\n"
        f"📊 Total Referrals: <b>{len(refs)}</b>\n"
        f"🪙 Total Earned: <b>{fmt_coins(len(refs) * reward)}</b>"
    )
    await edit_or_reply(query, text, referral_kb(me_url))


# =============================================================================
# Callback router
# =============================================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    if data == "menu_back":
        context.user_data.clear()
        await q.message.reply_text(
            f"👋 <b>Welcome, {q.from_user.first_name}!</b>\n\n"
            "🛍 <b>FF Autolikes Shop Bot</b>\n\n"
            "Choose an option below:",
            reply_markup=main_kb(uid), parse_mode="HTML"
        )
        return

    if data == "cancel_flow":
        context.user_data.clear()
        await safe_delete(context.bot, q.message.chat_id, q.message.message_id)
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=f"👋 <b>Welcome, {q.from_user.first_name}!</b>\n\n"
            "🛍 <b>FF Autolikes Shop Bot</b>\n\n"
            "Choose an option below:",
            reply_markup=main_kb(uid), parse_mode="HTML"
        )
        return

    if data == "menu_buy_auto":
        await show_buy_auto(q, context)
        return
    if data == "menu_my_auto":
        await show_my_autolikes(q)
        return
    if data == "menu_redeem":
        context.user_data.clear(); context.user_data["flow"] = "redeem"
        await edit_or_reply(q, "🎟 <b>Enter your redeem code</b>", cancel_kb())
        return
    if data == "menu_buy_coins":
        await show_buy_coins(q, context)
        return
    if data == "menu_balance":
        await show_balance(q)
        return
    if data == "menu_earn":
        await show_earn(q)
        return
    if data == "menu_help":
        await edit_or_reply(q,
            "❓ <b>Help & Support</b>\n\n"
            "Use the buttons in the main menu.\n\n"
            "For payment verification or any issue, contact admin.",
            contact_admin_kb())
        return

    # ---------- AutoLike flow ----------
    if data.startswith("auto_plan_"):
        plan_id = data[len("auto_plan_"):]
        plan = find_plan(plan_id)
        if not plan or not plan.get("active", True):
            await q.answer("Plan unavailable", show_alert=True); return
        context.user_data.update({"flow": "auto", "plan_id": plan_id})
        await edit_or_reply(q,
            f"📦 <b>{escape(str(plan.get('name','Plan')))}</b>\n\nSelect a package:",
            plan_packages_kb(plan))
        return

    # Legacy callback compatibility for old 220/500 buttons.
    if data in ("auto_pkg_220", "auto_pkg_500"):
        plan_id = "220" if data.endswith("220") else "500"
        plan = find_plan(plan_id)
        if plan:
            context.user_data.update({"flow": "auto", "plan_id": plan_id})
            await edit_or_reply(q, f"📦 <b>{escape(str(plan.get('name','Plan')))}</b>\n\nSelect a package:", plan_packages_kb(plan))
        return

    if data.startswith("auto_pkg_"):
        raw = data[len("auto_pkg_"):]
        try:
            plan_id, pkg_id = raw.split("_", 1)
        except ValueError:
            await q.answer("Package unavailable", show_alert=True); return
        plan = find_plan(plan_id)
        pkg = find_package(plan, pkg_id)
        if not plan or not pkg or not plan.get("active", True) or not pkg.get("active", True):
            await q.answer("Package unavailable", show_alert=True); return
        context.user_data.update({"flow": "auto", "plan_id": plan_id, "package_id": pkg_id})
        await edit_or_reply(q,
            f"📦 <b>{escape(str(pkg.get('name','Package')))}</b>\n\n"
            f"Coins used: <b>{fmt_coins(pkg.get('coins',0))}</b>\n"
            f"Duration: <b>{int(pkg.get('days',1))} day(s)</b>\n\n"
            "Select region:", region_kb())
        return

    if data.startswith("auto_region_"):
        region = data.replace("auto_region_", "")
        context.user_data["region"] = region
        context.user_data["flow"] = "auto_uid"
        await edit_or_reply(q,
            f"🌍 Region: <b>{REGION_NAMES.get(region, region)}</b>\n\n"
            "Please enter the Free Fire UID:",
            cancel_kb())
        return

    if data == "auto_confirm":
        if context.user_data.get("flow") != "auto_confirm":
            await q.answer("Order session expired. Start again.", show_alert=True); return
        u = user_record(q.from_user)
        plan = find_plan(context.user_data.get("plan_id"))
        pkg = find_package(plan, context.user_data.get("package_id"))
        if not plan or not pkg or not pkg.get("active", True):
            context.user_data.clear(); await q.answer("Package is no longer available.", show_alert=True); return
        price = coins(pkg.get("coins", 0))
        if coins(u.get("coins", 0)) < price:
            context.user_data.clear()
            await edit_or_reply(q,
                f"❌ <b>Insufficient Coins</b>\n\nRequired: {fmt_coins(price)}\nYour balance: {fmt_coins(u.get('coins',0))}",
                InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Coins", callback_data="menu_buy_coins")],
                                      [InlineKeyboardButton("⬅️ Back", callback_data="menu_back")]]))
            return
        order_id = uuid.uuid4().hex[:10].upper()
        u["coins"] = coins(u.get("coins", 0) - price)
        order = {
            "id": order_id,
            "user_id": q.from_user.id,
            "name": q.from_user.full_name,
            "username": q.from_user.username or "",
            "plan": plan.get("id"),
            "plan_name": plan.get("name"),
            "package": pkg.get("id"),
            "package_title": pkg.get("name"),
            "coins": price,
            "days": int(pkg.get("days", 1)),
            "uid": context.user_data["uid"],
            "region": context.user_data["region"],
            "status": "pending",
            "created_at": iso_now(),
        }
        db["autolike_orders"].append(order)
        save_db()
        context.user_data.clear()
        summary = (
            "🧾 <b>Order Submitted Successfully</b>\n\n"
            f"Order ID: <code>{order_id}</code>\n"
            f"Plan: <b>{escape(str(order['plan_name']))}</b>\n"
            f"Package: <b>{escape(str(order['package_title']))}</b>\n"
            f"UID: <code>{order['uid']}</code>\n"
            f"Region: {REGION_NAMES.get(order['region'], order['region'])}\n"
            f"Days: {order['days']}\n"
            f"Coins deducted: <b>{fmt_coins(price)}</b>\n"
            f"Balance: <b>{fmt_coins(u['coins'])}</b>\n\n"
            "⏳ Your order is waiting for admin approval."
        )
        await edit_or_reply(q, summary, back_menu_kb())
        await send_admins(context,
            "🛒 <b>New AutoLike Order</b>\n\n"
            f"Order ID: <code>{order_id}</code>\n"
            f"User: {escape(str(order['name']))} (@{escape(order['username'] or 'no_username')})\n"
            f"User ID: <code>{order['user_id']}</code>\n"
            f"Plan: {escape(str(order['plan_name']))}\n"
            f"Package: {escape(str(order['package_title']))}\n"
            f"UID: <code>{order['uid']}</code>\n"
            f"Region: {REGION_NAMES.get(order['region'], order['region'])}\n"
            f"Days: {order['days']}\n"
            f"Coins: {fmt_coins(price)}",
            admin_order_actions(order_id))
        return

    # ---------- Coin payment flow ----------
    if data.startswith("coin_pkg_"):
        pricing_id = data[len("coin_pkg_"):]
        item = next((x for x in db["config"].get("coin_pricing", []) if str(x.get("id")) == pricing_id and x.get("active", True)), None)
        if not item:
            await q.answer("Pricing unavailable", show_alert=True); return
        amount = int(item.get("amount", 0))
        coin_amount = coins(item.get("coins", 0))
        context.user_data.update({"flow": "coin_payment", "pay_amount": amount, "pay_coins": coin_amount})
        text = payment_text(amount, coin_amount)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📸 I Have Paid", callback_data="coin_paid")],
            [InlineKeyboardButton("📹 How to Pay", callback_data="how_to_pay")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_flow")],
        ])
        try:
            # Always generate a fresh QR for the exact selected amount.
            qr_image = make_payment_qr(amount)
            await q.message.reply_photo(
                photo=qr_image, caption=text, parse_mode="HTML", reply_markup=buttons
            )
            await safe_delete(context.bot, q.message.chat_id, q.message.message_id)
        except Exception as e:
            print("QR generation/send error:", e)
            await edit_or_reply(q, text, buttons)
        return

    if data == "how_to_pay":
        url = db["config"].get("how_to_pay_url", "")
        if url:
            await q.message.reply_text(
                f"📹 <b>{db['config'].get('how_to_pay_text','How to Pay')}</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Open How to Pay", url=url)],
                    [InlineKeyboardButton("⬅️ Back", callback_data="menu_buy_coins")],
                ])
            )
        else:
            await q.answer("How-to-pay link is not set yet.", show_alert=True)
        return

    if data == "coin_paid":
        if context.user_data.get("flow") != "coin_payment":
            await q.answer("Payment session expired. Start again.", show_alert=True); return
        context.user_data["flow"] = "coin_photo"
        await edit_or_reply(q,
            "📸 <b>Send screenshot of your payment</b>\n\n"
            "Please send the payment screenshot here.", cancel_kb())
        return

    if data == "verify_enter_code":
        context.user_data.clear(); context.user_data["flow"] = "verify_code"
        await edit_or_reply(q, "🔑 <b>Enter verification code</b>", cancel_kb("cancel_flow"))
        return

    # ---------- Earn ----------
    if data == "earn_verify":
        await show_verify_tasks(q); return
    if data == "earn_ref":
        await show_referral(q, context); return

    # ---------- Admin ----------
    if data.startswith("admin_"):
        if not is_owner(uid):
            await q.answer("Admin only.", show_alert=True); return
        await admin_callback(q, context, data)
        return


# =============================================================================
# Message handler: UID / redeem / photo / UTR / verify code / admin prompts
# =============================================================================
async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = user_record(update.effective_user)
    flow = context.user_data.get("flow")

    # Photo is only accepted in the coin-payment screenshot step.
    if update.message.photo and flow == "coin_photo":
        photo = update.message.photo[-1]
        context.user_data["payment_photo_id"] = photo.file_id
        context.user_data["flow"] = "coin_utr"
        await update.message.reply_text(
            "🔢 <b>Enter payment UTR / transaction ID</b>\n\n"
            "Send the UTR shown in your payment app.", parse_mode="HTML")
        return

    if not update.message.text:
        return
    text = update.message.text.strip()

    # Reply-keyboard main menu always has priority over an unfinished flow.
    if text in MENU_TEXT_TO_CALLBACK:
        data = MENU_TEXT_TO_CALLBACK[text]
        context.user_data.clear()
        if data == "menu_buy_auto":
            context.user_data["flow"] = "auto"
            await update.message.reply_text(
                "🛒 <b>Select Autolike Plan</b>\n\nChoose your package type:",
                reply_markup=package_kb(), parse_mode="HTML"
            )
        elif data == "menu_my_auto":
            # Reuse a tiny message-like adapter by directly rendering the list.
            uid = str(update.effective_user.id)
            orders = [o for o in db["autolike_orders"] if str(o.get("user_id")) == uid and o.get("status") == "approved"]
            if not orders:
                body = "📁 <b>My Autolikes</b>\n\nNo orders show here yet.\n\nYour accepted AutoLike orders will appear here."
            else:
                lines = []
                for i, o in enumerate(reversed(orders[-20:]), 1):
                    lines.append(f"<b>{i}. {o['package_title']}</b>\nUID: <code>{o['uid']}</code>\nRegion: {REGION_NAMES.get(o['region'], o['region'])}\nDays: {o['days']}\nStatus: {o['status'].title()}\nAccepted: {o.get('approved_at','N/A')}")
                body = "📁 <b>My Autolikes</b>\n\n" + "\n\n".join(lines)
            await update.message.reply_text(body, reply_markup=back_menu_kb(), parse_mode="HTML")
        elif data == "menu_redeem":
            context.user_data["flow"] = "redeem"
            await update.message.reply_text("🎟 <b>Enter your redeem code</b>", reply_markup=cancel_kb(), parse_mode="HTML")
        elif data == "menu_buy_coins":
            context.user_data["flow"] = "coins"
            await update.message.reply_text("💰 <b>Select UPI Package</b>\n\nChoose the amount you want to pay:", reply_markup=payment_packages_kb(), parse_mode="HTML")
        elif data == "menu_balance":
            u2 = db["users"].get(str(update.effective_user.id), {})
            await update.message.reply_text(
                "💳 <b>My Balance</b>\n\n"
                f"Current balance: <b>{fmt_coins(u2.get('coins',0))} coins</b>\n"
                f"Total bought: <b>{fmt_coins(u2.get('total_bought',0))} coins</b>\n"
                f"Total earned: <b>{fmt_coins(u2.get('total_earned',0))} coins</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Coins", callback_data="menu_buy_coins")]]), parse_mode="HTML"
            )
        elif data == "menu_earn":
            await update.message.reply_text("👥 <b>Earn Coins</b>\n\nChoose a method:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Verify & Earn", callback_data="earn_verify")],[InlineKeyboardButton("👥 Refer & Earn", callback_data="earn_ref")]]), parse_mode="HTML")
        elif data == "menu_help":
            await update.message.reply_text("❓ <b>Help & Support</b>\n\nUse the buttons in the main menu.\n\nFor payment verification or any issue, contact admin.", reply_markup=contact_admin_kb(), parse_mode="HTML")
        return

    if flow == "auto_uid":
        if not valid_uid(text):
            await update.message.reply_text("❌ Invalid UID. Please enter a numeric Free Fire UID (6–15 digits).", parse_mode="HTML")
            return
        context.user_data["uid"] = text
        context.user_data["flow"] = "auto_confirm"
        plan = find_plan(context.user_data.get("plan_id"))
        pkg = find_package(plan, context.user_data.get("package_id"))
        if not plan or not pkg or not pkg.get("active", True):
            context.user_data.clear()
            await update.message.reply_text("❌ This package is no longer available.", reply_markup=main_kb(update.effective_user.id), parse_mode="HTML")
            return
        summary = (
            "🧾 <b>Order Summary</b>\n\n"
            f"Plan: <b>{escape(str(plan.get('name','Plan')))}</b>\n"
            f"Package: <b>{escape(str(pkg.get('name','Package')))}</b>\n"
            f"Duration: <b>{int(pkg.get('days',1))} day(s)</b>\n"
            f"UID: <code>{text}</code>\n"
            f"Region: <b>{REGION_NAMES.get(context.user_data['region'], context.user_data['region'])}</b>\n"
            f"Price: <b>{fmt_coins(pkg.get('coins',0))} coins</b>\n\n"
            "Confirm the order below."
        )
        await update.message.reply_text(summary, reply_markup=summary_kb(), parse_mode="HTML")
        return

    if flow == "redeem":
        code = text.upper()
        item = db["redeem_codes"].get(code)
        if not item or not item.get("active", True):
            await update.message.reply_text("❌ Invalid or inactive redeem code.", reply_markup=back_menu_kb(), parse_mode="HTML")
            context.user_data.clear(); return
        if str(update.effective_user.id) in item.setdefault("used_by", []):
            await update.message.reply_text("⚠️ You have already used this code.", reply_markup=back_menu_kb(), parse_mode="HTML")
            context.user_data.clear(); return
        reward = coins(item.get("coins", 0))
        item["used_by"].append(str(update.effective_user.id))
        u["coins"] = coins(u.get("coins", 0) + reward)
        u["total_earned"] = coins(u.get("total_earned", 0) + reward)
        db["stats"]["total_earned_coins"] = coins(db["stats"].get("total_earned_coins", 0) + reward)
        if item.get("max_uses") and len(item["used_by"]) >= int(item["max_uses"]):
            item["active"] = False
        save_db()
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ <b>Redeem Successful</b>\n\nYou received <b>{fmt_coins(reward)} coins</b>.\nCurrent balance: <b>{fmt_coins(u['coins'])}</b>",
            reply_markup=back_menu_kb(), parse_mode="HTML")
        return

    if flow == "coin_utr":
        if not valid_utr(text):
            await update.message.reply_text("❌ Invalid UTR. Enter 6–40 letters/numbers only.", parse_mode="HTML")
            return
        order_id = uuid.uuid4().hex[:10].upper()
        order = {
            "id": order_id,
            "user_id": update.effective_user.id,
            "name": update.effective_user.full_name,
            "username": update.effective_user.username or "",
            "amount": context.user_data["pay_amount"],
            "coins": context.user_data["pay_coins"],
            "utr": text,
            "photo_id": context.user_data.get("payment_photo_id", ""),
            "status": "verifying",
            "created_at": iso_now(),
        }
        db["coin_orders"].append(order)
        save_db()
        context.user_data.clear()

        wait = await update.message.reply_text(
            "⏳ <b>Auto-verifying payment details...</b>", parse_mode="HTML"
        )
        order["verification_chat_id"] = update.effective_chat.id
        order["verification_message_id"] = wait.message_id
        save_db()
        await send_admins(context,
            "💳 <b>New Coin Payment</b>\n\n"
            f"Order ID: <code>{order_id}</code>\n"
            f"User: {order['name']} (@{order['username'] or 'no_username'})\n"
            f"User ID: <code>{order['user_id']}</code>\n"
            f"Amount: ₹{order['amount']}\n"
            f"Coins: {order['coins']}\n"
            f"UTR: <code>{order['utr']}</code>",
            admin_payment_actions(order_id), photo=order["photo_id"] or None)
        # Run the 10-minute changing verification status in the background.
        asyncio.create_task(payment_verification_loop(context, order_id))
        return

    if flow == "verify_code":
        code = text.upper()
        matching = [t for t in db["verify_tasks"] if t.get("active", True) and str(t.get("code", "")).upper() == code]
        if not matching:
            await update.message.reply_text("❌ Invalid or inactive verification code.", reply_markup=back_menu_kb(), parse_mode="HTML")
            context.user_data.clear(); return
        task = matching[0]
        key = f"{update.effective_user.id}:{task.get('id')}"
        if key in db["verify_redemptions"]:
            await update.message.reply_text("⚠️ This verification code has already been used by you.", reply_markup=back_menu_kb(), parse_mode="HTML")
            context.user_data.clear(); return
        reward = coins(task.get("reward", db["config"].get("verify_reward", 0.5)))
        db["verify_redemptions"][key] = iso_now()
        u["coins"] = coins(u.get("coins", 0) + reward)
        u["total_earned"] = coins(u.get("total_earned", 0) + reward)
        db["stats"]["total_earned_coins"] = coins(db["stats"].get("total_earned_coins", 0) + reward)
        save_db(); context.user_data.clear()
        await update.message.reply_text(
            f"✅ <b>Verification Successful</b>\n\nYou earned <b>{fmt_coins(reward)} coins</b>.\nBalance: <b>{fmt_coins(u['coins'])}</b>",
            reply_markup=back_menu_kb(), parse_mode="HTML")
        return

    # Admin input modes are handled below.
    if is_owner(update.effective_user.id) and flow and flow.startswith("admin_"):
        await handle_admin_text(update, context, text)


# =============================================================================
# Admin UI
# =============================================================================
async def admin_callback(q, context, data):
    if data == "admin_panel":
        context.user_data.clear()
        await edit_or_reply(q, "🔐 <b>Admin Panel</b>\n\nChoose what you want to manage:", admin_panel_kb())
        return

    if data == "admin_auto_pending":
        orders = [o for o in db["autolike_orders"] if o.get("status") == "pending"]
        if not orders:
            await edit_or_reply(q, "🧾 <b>Pending AutoLike Orders</b>\n\nNo pending orders.", admin_back_kb()); return
        # Show the first pending order; admin can return and process the next.
        o = orders[0]
        await edit_or_reply(q, format_admin_auto(o), admin_order_actions(o["id"]))
        return

    if data.startswith("admin_auto_approve_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["autolike_orders"] if x["id"] == oid), None)
        if not o or o.get("status") != "pending":
            await q.answer("Order is no longer pending.", show_alert=True); return
        o["status"] = "approved"
        o["approved_at"] = iso_now()
        expiry = (now_ist().date() + timedelta(days=int(o["days"]))).strftime("%Y-%m-%d")
        active = {
            "order_id": o["id"], "user_id": o["user_id"], "uid": o["uid"], "region": o["region"],
            "package": o["package"], "package_title": o["package_title"], "days": o["days"],
            "expiry_date": expiry, "status": "active", "added_at": iso_now()
        }
        db["autolikes"].append(active)
        save_db()
        await notify_user(context,
            o["user_id"],
            "✅ <b>AutoLike Order Approved</b>\n\n"
            f"Order: <code>{o['id']}</code>\n"
            f"UID: <code>{o['uid']}</code>\n"
            f"Package: {o['package_title']}\n\n"
            "🕓 Your likes will be provided around <b>4:00 AM IST</b> as scheduled.",
            back_menu_kb())
        await edit_or_reply(q, "✅ Order approved.\n\n" + format_admin_auto(o), admin_back_kb())
        return

    if data.startswith("admin_auto_reject_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["autolike_orders"] if x["id"] == oid), None)
        if not o or o.get("status") != "pending":
            await q.answer("Order is no longer pending.", show_alert=True); return
        o["status"] = "rejected"; o["rejected_at"] = iso_now(); o["refund"] = o["coins"]
        u = user_record_from_id(o["user_id"])
        u["coins"] = coins(u.get("coins", 0) + o["coins"])
        save_db()
        await notify_user(context, o["user_id"],
                          "❌ <b>AutoLike Order Rejected</b>\n\n"
                          f"Order: <code>{o['id']}</code>\n"
                          f"Your <b>{fmt_coins(o['coins'])} coins</b> have been refunded.", back_menu_kb())
        await edit_or_reply(q, "❌ Order rejected and coins refunded.\n\n" + format_admin_auto(o), admin_back_kb())
        return

    if data.startswith("admin_auto_manage_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["autolike_orders"] if x["id"] == oid), None)
        if not o:
            await q.answer("Order not found.", show_alert=True); return
        await edit_or_reply(q, format_admin_auto(o) + "\n\n⚙️ Manage options:", InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Mark Completed", callback_data=f"admin_auto_complete_{oid}")],
            [InlineKeyboardButton("🗑 Remove Order", callback_data=f"admin_auto_remove_{oid}")],
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")],
        ]))
        return

    if data.startswith("admin_auto_complete_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["autolike_orders"] if x["id"] == oid), None)
        if o:
            o["status"] = "completed"; o["completed_at"] = iso_now()
            for al in db["autolikes"]:
                if al.get("order_id") == oid: al["status"] = "completed"
            save_db()
            await notify_user(context, o["user_id"], f"✅ <b>AutoLike Completed</b>\n\nOrder <code>{oid}</code> is completed.", back_menu_kb())
        await edit_or_reply(q, "Order marked completed.", admin_back_kb()); return

    if data.startswith("admin_auto_remove_"):
        oid = data.rsplit("_", 1)[-1]
        db["autolike_orders"] = [o for o in db["autolike_orders"] if o["id"] != oid]
        db["autolikes"] = [a for a in db["autolikes"] if a.get("order_id") != oid]
        save_db(); await edit_or_reply(q, "🗑 Order removed.", admin_back_kb()); return

    if data == "admin_coin_pending":
        orders = [o for o in db["coin_orders"] if o.get("status") in ("verifying", "pending", "manual_review")]
        if not orders:
            await edit_or_reply(q, "💳 <b>Pending Coin Payments</b>\n\nNo pending payments.", admin_back_kb()); return
        o = orders[0]
        await edit_or_reply(q, format_admin_payment(o), admin_payment_actions(o["id"]))
        return

    if data.startswith("admin_coin_approve_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["coin_orders"] if x["id"] == oid), None)
        if not o or o.get("status") not in ("verifying", "pending", "manual_review"):
            await q.answer("Payment is no longer pending.", show_alert=True); return
        o["status"] = "approved"; o["approved_at"] = iso_now()
        u = user_record_from_id(o["user_id"])
        u["coins"] = coins(u.get("coins", 0) + o["coins"])
        u["total_bought"] = coins(u.get("total_bought", 0) + o["coins"])
        db["stats"]["total_bought_coins"] = coins(db["stats"].get("total_bought_coins", 0) + o["coins"])
        save_db()
        await finish_payment_wait_message(
            context, o,
            "✅ <b>Payment Approved</b>\n\n"
            f"Amount: ₹{o['amount']}\nCoins added: <b>{fmt_coins(o['coins'])}</b>\n"
            f"New balance: <b>{fmt_coins(u['coins'])}</b>",
            main_kb(o["user_id"]),
        )
        await notify_user(context, o["user_id"],
                          "✅ <b>Payment Approved</b>\n\n"
                          f"Amount: ₹{o['amount']}\nCoins added: <b>{fmt_coins(o['coins'])}</b>\n"
                          f"New balance: <b>{fmt_coins(u['coins'])}</b>", back_menu_kb())
        await edit_or_reply(q, "✅ Payment approved. Coins added.\n\n" + format_admin_payment(o), admin_back_kb()); return

    if data.startswith("admin_coin_reject_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["coin_orders"] if x["id"] == oid), None)
        if o:
            if o.get("status") not in ("verifying", "pending", "manual_review"):
                await q.answer("Payment is no longer pending.", show_alert=True); return
            o["status"] = "rejected"; o["rejected_at"] = iso_now(); save_db()
            await finish_payment_wait_message(
                context, o,
                "❌ <b>Payment Verification Failed</b>\n\n"
                f"Order: <code>{oid}</code>\nPlease contact admin if you think this is an error.",
                contact_admin_kb(),
            )
            await notify_user(context, o["user_id"],
                              "❌ <b>Payment Verification Failed</b>\n\n"
                              f"Order: <code>{oid}</code>\nPlease contact admin if you think this is an error.", contact_admin_kb())
        await edit_or_reply(q, "❌ Payment rejected.\n\n" + format_admin_payment(o), admin_back_kb()); return

    if data.startswith("admin_coin_manage_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["coin_orders"] if x["id"] == oid), None)
        if not o: await q.answer("Payment not found.", show_alert=True); return
        await edit_or_reply(q, format_admin_payment(o) + "\n\n⚙️ Manage:", InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Approve + Edit Balance", callback_data=f"admin_coin_custom_{oid}")],
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")],
        ])); return

    if data.startswith("admin_coin_custom_"):
        oid = data.rsplit("_", 1)[-1]
        o = next((x for x in db["coin_orders"] if x["id"] == oid), None)
        if not o: return
        context.user_data["flow"] = "admin_set_balance_order"
        context.user_data["admin_order_id"] = oid
        await edit_or_reply(q, "💰 Enter the exact number of coins to add to this user's balance:", admin_back_kb()); return

    if data == "admin_users":
        await edit_or_reply(q,
            "👤 <b>Manage Users</b>\n\nEnter a Telegram user ID to manage:",
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")]]))
        context.user_data["flow"] = "admin_user_id"; return

    if data == "admin_codes":
        await edit_or_reply(q, "🎟 <b>Redeem Codes</b>\n\nChoose:", InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Create Code", callback_data="admin_code_create")],
            [InlineKeyboardButton("📋 List Codes", callback_data="admin_code_list")],
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")],
        ])); return

    if data == "admin_code_create":
        context.user_data["flow"] = "admin_code_create"
        await edit_or_reply(q, "🎟 Send code and coin reward like:\n<code>WELCOME50 50</code>", admin_back_kb()); return

    if data == "admin_code_list":
        items = []
        for code, item in db["redeem_codes"].items():
            items.append(f"<code>{code}</code> — {fmt_coins(item.get('coins',0))} coins — {'active' if item.get('active',True) else 'inactive'} — used {len(item.get('used_by',[]))}")
        await edit_or_reply(q, "🎟 <b>Codes</b>\n\n" + ("\n".join(items) if items else "No codes."), admin_back_kb()); return

    if data == "admin_verify":
        await edit_or_reply(q, "🔗 <b>Verify & Earn</b>\n\nManage verification links.", InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Verification Link", callback_data="admin_verify_add")],
            [InlineKeyboardButton("📋 Manage Verification Links", callback_data="admin_verify_list")],
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")],
        ])); return

    if data == "admin_verify_add":
        context.user_data["flow"] = "admin_verify_add"
        await edit_or_reply(q, "🔗 <b>Add Verification Link</b>\n\nSend exactly:\n<code>Name | URL | Details | CODE | Reward</code>", admin_back_kb()); return

    if data == "admin_settings":
        await edit_or_reply(q,
            "⚙️ <b>Settings</b>\n\nChoose:", InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 UPI / Payment Details", callback_data="admin_set_payment")],
                [InlineKeyboardButton("🛒 Manage Plans", callback_data="admin_manage_plans")],
                [InlineKeyboardButton("💰 Manage Pricing", callback_data="admin_manage_pricing")],
                [InlineKeyboardButton("📹 How to Pay Link", callback_data="admin_set_howto")],
                [InlineKeyboardButton("👤 Admin Contact", callback_data="admin_set_contact")],
                [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")],
            ])); return

    if data == "admin_set_payment":
        context.user_data["flow"] = "admin_payment_settings"
        await edit_or_reply(q, "💳 Send payment details as:\n<code>UPI_ID | NAME | QR_FILE_ID(optional)</code>", admin_back_kb()); return

    # ---------- Verification task management ----------
    if data == "admin_verify_list":
        rows = []
        for t in db["verify_tasks"]:
            status = "🟢" if t.get("active", True) else "🔴"
            rows.append([InlineKeyboardButton(f"{status} {str(t.get('title','Verification'))}", callback_data=f"admin_verify_view_{t.get('id')}")])
        rows.append([InlineKeyboardButton("➕ Add Verification Link", callback_data="admin_verify_add")])
        rows.append([InlineKeyboardButton("⬅️ Verify & Earn", callback_data="admin_verify")])
        await edit_or_reply(q, "🔗 <b>Verification Links</b>\n\nTap a link to manage its name, URL, details, code, reward and status.", InlineKeyboardMarkup(rows)); return

    if data.startswith("admin_verify_view_"):
        tid = data[len("admin_verify_view_"):]
        task = next((t for t in db["verify_tasks"] if str(t.get("id")) == tid), None)
        if not task: await q.answer("Task not found.", show_alert=True); return
        status = "🟢 Active" if task.get("active", True) else "🔴 Inactive"
        details = task.get("details") or "No details set."
        text = (f"🔗 <b>{escape(str(task.get('title','Verification')))}</b>\n\n"
                f"Status: <b>{status}</b>\n"
                f"Link: <code>{escape(str(task.get('url','')))}</code>\n"
                f"Details: {escape(str(details))}\n"
                f"Code: <code>{escape(str(task.get('code','')))}</code>\n"
                f"Reward: <b>{fmt_coins(task.get('reward',0))} coins</b>")
        toggle = "🔴 Make Inactive" if task.get("active", True) else "🟢 Make Active"
        await edit_or_reply(q, text, InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Edit Name", callback_data=f"admin_verify_edit_name_{tid}"), InlineKeyboardButton("🔗 Edit Link", callback_data=f"admin_verify_edit_url_{tid}")],
            [InlineKeyboardButton("📝 Edit Details", callback_data=f"admin_verify_edit_details_{tid}"), InlineKeyboardButton("🔑 Edit Code", callback_data=f"admin_verify_edit_code_{tid}")],
            [InlineKeyboardButton("🪙 Edit Reward", callback_data=f"admin_verify_edit_reward_{tid}")],
            [InlineKeyboardButton(toggle, callback_data=f"admin_verify_status_{tid}"), InlineKeyboardButton("🗑 Delete", callback_data=f"admin_verify_delete_{tid}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_verify_list")],
        ])); return

    if data.startswith("admin_verify_status_"):
        tid=data[len("admin_verify_status_"):]
        task=next((t for t in db["verify_tasks"] if str(t.get("id"))==tid),None)
        if task:
            task["active"]=not task.get("active",True); save_db()
            await edit_or_reply(q,"✅ Verification link status updated.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data=f"admin_verify_view_{tid}")]]))
        return

    if data.startswith("admin_verify_delete_"):
        tid=data[len("admin_verify_delete_"):]
        db["verify_tasks"]=[t for t in db["verify_tasks"] if str(t.get("id"))!=tid]; save_db()
        await edit_or_reply(q,"🗑 Verification link deleted.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Verification Links",callback_data="admin_verify_list")]])); return

    for prefix, field, prompt, flow_name in [
        ("admin_verify_edit_name_","title","✏️ Send the new verification link name:","admin_verify_edit_name"),
        ("admin_verify_edit_url_","url","🔗 Send the new verification URL:","admin_verify_edit_url"),
        ("admin_verify_edit_details_","details","📝 Send the new verification details:","admin_verify_edit_details"),
        ("admin_verify_edit_code_","code","🔑 Send the new verification code:","admin_verify_edit_code"),
        ("admin_verify_edit_reward_","reward","🪙 Send the reward in coins:","admin_verify_edit_reward"),
    ]:
        if data.startswith(prefix):
            tid=data[len(prefix):]
            context.user_data.update({"flow":flow_name,"admin_verify_id":tid})
            await edit_or_reply(q,prompt,admin_back_kb()); return

    # ---------- Plan/package management ----------
    if data == "admin_manage_plans":
        rows=[[InlineKeyboardButton(f"{'🟢' if p.get('active',True) else '🔴'} {str(p.get('name','Plan'))}", callback_data=f"admin_plan_view_{p['id']}")] for p in get_plans(True)]
        rows.append([InlineKeyboardButton("➕ Add Plan", callback_data="admin_plan_add")])
        rows.append([InlineKeyboardButton("⬅️ Settings", callback_data="admin_settings")])
        await edit_or_reply(q,"🛒 <b>Manage Plans</b>\n\nSelect a plan to manage it, or add a new plan.",InlineKeyboardMarkup(rows)); return

    if data == "admin_plan_add":
        context.user_data["flow"]="admin_plan_add"
        await edit_or_reply(q,"➕ <b>Add Plan</b>\n\nSend the plan name. This exact name will be shown on the plan button to users.",admin_back_kb()); return

    if data.startswith("admin_plan_view_"):
        pid=data[len("admin_plan_view_"):]
        plan=find_plan(pid)
        if not plan: await q.answer("Plan not found.",show_alert=True); return
        status="🟢 Active" if plan.get("active",True) else "🔴 Inactive"
        count=len(plan.get("packages",{}))
        toggle="🔴 Make Inactive" if plan.get("active",True) else "🟢 Make Active"
        await edit_or_reply(q,f"🛒 <b>{escape(str(plan.get('name','Plan')))}</b>\n\nStatus: <b>{status}</b>\nPackages: <b>{count}</b>",InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Manage Packages",callback_data=f"admin_plan_packages_{pid}")],
            [InlineKeyboardButton("✏️ Edit Name",callback_data=f"admin_plan_edit_name_{pid}")],
            [InlineKeyboardButton(toggle,callback_data=f"admin_plan_status_{pid}"),InlineKeyboardButton("🗑 Delete",callback_data=f"admin_plan_delete_{pid}")],
            [InlineKeyboardButton("⬅️ Back",callback_data="admin_manage_plans")],
        ])); return

    if data.startswith("admin_plan_status_"):
        pid=data[len("admin_plan_status_"):]; plan=find_plan(pid)
        if plan:
            plan["active"]=not plan.get("active",True); save_db()
            await edit_or_reply(q,"✅ Plan status updated.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data=f"admin_plan_view_{pid}")]]))
        return

    if data.startswith("admin_plan_delete_"):
        pid=data[len("admin_plan_delete_"):]
        if pid in db["config"].get("plans",{}): del db["config"]["plans"][pid]; save_db()
        await edit_or_reply(q,"🗑 Plan deleted.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Manage Plans",callback_data="admin_manage_plans")]])); return

    if data.startswith("admin_plan_edit_name_"):
        pid=data[len("admin_plan_edit_name_"):]; context.user_data.update({"flow":"admin_plan_edit_name","admin_plan_id":pid})
        await edit_or_reply(q,"✏️ Send the new plan name:",admin_back_kb()); return

    if data.startswith("admin_plan_packages_"):
        pid=data[len("admin_plan_packages_"):]; plan=find_plan(pid)
        if not plan: await q.answer("Plan not found.",show_alert=True); return
        rows=[[InlineKeyboardButton(f"{'🟢' if pkg.get('active',True) else '🔴'} {str(pkg.get('name','Package'))}",callback_data=f"admin_pkg_view_{pid}_{pkg['id']}")] for pkg in plan.get("packages",{}).values()]
        rows.append([InlineKeyboardButton("➕ Add Package",callback_data=f"admin_pkg_add_{pid}")])
        rows.append([InlineKeyboardButton("⬅️ Back",callback_data=f"admin_plan_view_{pid}")])
        await edit_or_reply(q,f"📦 <b>Packages — {escape(str(plan.get('name','Plan')))}</b>\n\nSelect a package to edit, activate/deactivate or delete it.",InlineKeyboardMarkup(rows)); return

    if data.startswith("admin_pkg_add_"):
        pid=data[len("admin_pkg_add_"):]; context.user_data.update({"flow":"admin_pkg_add","admin_plan_id":pid})
        await edit_or_reply(q,"➕ <b>Add Package</b>\n\nSend exactly:\n<code>Button Name | Coins | Days</code>\n\nThe Button Name is displayed exactly on the user's package button. Coins and Days control the actual purchase/expiry values.",admin_back_kb()); return

    if data.startswith("admin_pkg_view_"):
        raw=data[len("admin_pkg_view_"):]
        try: pid,pkgid=raw.split("_",1)
        except ValueError: await q.answer("Package not found.",show_alert=True); return
        plan=find_plan(pid); pkg=find_package(plan,pkgid)
        if not pkg: await q.answer("Package not found.",show_alert=True); return
        status="🟢 Active" if pkg.get("active",True) else "🔴 Inactive"
        toggle="🔴 Make Inactive" if pkg.get("active",True) else "🟢 Make Active"
        await edit_or_reply(q,f"📦 <b>{escape(str(pkg.get('name','Package')))}</b>\n\nStatus: <b>{status}</b>\nCoins: <b>{fmt_coins(pkg.get('coins',0))}</b>\nDays: <b>{int(pkg.get('days',1))}</b>",InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Edit Name",callback_data=f"admin_pkg_edit_name_{pid}_{pkgid}")],
            [InlineKeyboardButton("🪙 Edit Coins",callback_data=f"admin_pkg_edit_coins_{pid}_{pkgid}"),InlineKeyboardButton("📅 Edit Days",callback_data=f"admin_pkg_edit_days_{pid}_{pkgid}")],
            [InlineKeyboardButton(toggle,callback_data=f"admin_pkg_status_{pid}_{pkgid}"),InlineKeyboardButton("🗑 Delete",callback_data=f"admin_pkg_delete_{pid}_{pkgid}")],
            [InlineKeyboardButton("⬅️ Back",callback_data=f"admin_plan_packages_{pid}")],
        ])); return

    for prefix, flow_name, prompt in [
        ("admin_pkg_edit_name_","admin_pkg_edit_name","✏️ Send the new package button name:"),
        ("admin_pkg_edit_coins_","admin_pkg_edit_coins","🪙 Send the new coin cost:"),
        ("admin_pkg_edit_days_","admin_pkg_edit_days","📅 Send the new duration in days:"),
    ]:
        if data.startswith(prefix):
            raw=data[len(prefix):]
            try: pid,pkgid=raw.split("_",1)
            except ValueError: await q.answer("Package not found.",show_alert=True); return
            context.user_data.update({"flow":flow_name,"admin_plan_id":pid,"admin_package_id":pkgid})
            await edit_or_reply(q,prompt,admin_back_kb()); return

    if data.startswith("admin_pkg_status_"):
        raw=data[len("admin_pkg_status_"):]
        try: pid,pkgid=raw.split("_",1)
        except ValueError: return
        pkg=find_package(find_plan(pid),pkgid)
        if pkg:
            pkg["active"]=not pkg.get("active",True); save_db()
            await edit_or_reply(q,"✅ Package status updated.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data=f"admin_pkg_view_{pid}_{pkgid}")]]))
        return

    if data.startswith("admin_pkg_delete_"):
        raw=data[len("admin_pkg_delete_"):];
        try: pid,pkgid=raw.split("_",1)
        except ValueError: return
        plan=find_plan(pid)
        if plan and pkgid in plan.get("packages",{}): del plan["packages"][pkgid]; save_db()
        await edit_or_reply(q,"🗑 Package deleted.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Packages",callback_data=f"admin_plan_packages_{pid}")]])); return

    # ---------- Coin pricing management ----------
    if data == "admin_manage_pricing":
        rows=[]
        for item in db["config"].get("coin_pricing",[]):
            status="🟢" if item.get("active",True) else "🔴"
            rows.append([InlineKeyboardButton(f"{status} ₹{item.get('amount',0)} → {fmt_coins(item.get('coins',0))} coins",callback_data=f"admin_price_view_{item.get('id')}")])
        rows.append([InlineKeyboardButton("➕ Add Pricing",callback_data="admin_price_add")])
        rows.append([InlineKeyboardButton("⬅️ Settings",callback_data="admin_settings")])
        await edit_or_reply(q,"💰 <b>Manage Pricing</b>\n\nManage the ₹ amount → coins mapping shown in Buy Coins.",InlineKeyboardMarkup(rows)); return

    if data == "admin_price_add":
        context.user_data["flow"]="admin_price_add"
        await edit_or_reply(q,"➕ <b>Add Pricing</b>\n\nSend exactly:\n<code>₹ Amount | Coins</code>",admin_back_kb()); return

    if data.startswith("admin_price_view_"):
        pid=data[len("admin_price_view_"):]; item=next((x for x in db["config"].get("coin_pricing",[]) if str(x.get("id"))==pid),None)
        if not item: await q.answer("Pricing not found.",show_alert=True); return
        status="🟢 Active" if item.get("active",True) else "🔴 Inactive"
        toggle="🔴 Make Inactive" if item.get("active",True) else "🟢 Make Active"
        await edit_or_reply(q,f"💰 <b>₹{item.get('amount',0)} → {fmt_coins(item.get('coins',0))} coins</b>\n\nStatus: <b>{status}</b>",InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Edit ₹ Amount",callback_data=f"admin_price_edit_amount_{pid}"),InlineKeyboardButton("🪙 Edit Coins",callback_data=f"admin_price_edit_coins_{pid}")],
            [InlineKeyboardButton(toggle,callback_data=f"admin_price_status_{pid}"),InlineKeyboardButton("🗑 Delete",callback_data=f"admin_price_delete_{pid}")],
            [InlineKeyboardButton("⬅️ Back",callback_data="admin_manage_pricing")],
        ])); return

    for prefix, flow_name, prompt in [
        ("admin_price_edit_amount_","admin_price_edit_amount","✏️ Send the new ₹ amount:"),
        ("admin_price_edit_coins_","admin_price_edit_coins","🪙 Send the new coin amount:"),
    ]:
        if data.startswith(prefix):
            pid=data[len(prefix):]; context.user_data.update({"flow":flow_name,"admin_price_id":pid})
            await edit_or_reply(q,prompt,admin_back_kb()); return

    if data.startswith("admin_price_status_"):
        pid=data[len("admin_price_status_"):]; item=next((x for x in db["config"].get("coin_pricing",[]) if str(x.get("id"))==pid),None)
        if item: item["active"]=not item.get("active",True); save_db(); await edit_or_reply(q,"✅ Pricing status updated.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data=f"admin_price_view_{pid}")]]))
        return

    if data.startswith("admin_price_delete_"):
        pid=data[len("admin_price_delete_"):]; db["config"]["coin_pricing"]=[x for x in db["config"].get("coin_pricing",[]) if str(x.get("id"))!=pid]; save_db()
        await edit_or_reply(q,"🗑 Pricing deleted.",InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Pricing",callback_data="admin_manage_pricing")]])); return

    if data == "admin_set_howto":
        context.user_data["flow"] = "admin_howto"
        await edit_or_reply(q, "📹 Send the How-to-Pay URL (Telegram video/file link or public URL).", admin_back_kb()); return

    if data == "admin_set_contact":
        context.user_data["flow"] = "admin_contact"
        await edit_or_reply(q, "👤 Send admin Telegram username, e.g. <code>@nrzravi</code>", admin_back_kb()); return

    if data == "admin_active":
        active = [a for a in db["autolikes"] if a.get("status") == "active"]
        if not active:
            text = "📋 <b>Active AutoLikes</b>\n\nNone."
        else:
            text = "📋 <b>Active AutoLikes</b>\n\n" + "\n\n".join(
                f"UID <code>{a['uid']}</code> | {REGION_NAMES.get(a['region'],a['region'])} | {a['package_title']} | expires {a['expiry_date']}"
                for a in active)
        await edit_or_reply(q, text, admin_back_kb()); return


def format_admin_auto(o):
    return (
        "🛒 <b>AutoLike Order</b>\n\n"
        f"Order: <code>{o['id']}</code>\n"
        f"User: {o.get('name','')} (@{o.get('username') or 'no_username'})\n"
        f"User ID: <code>{o['user_id']}</code>\n"
        f"Package: {o['package_title']}\n"
        f"UID: <code>{o['uid']}</code>\n"
        f"Region: {REGION_NAMES.get(o['region'],o['region'])}\n"
        f"Days: {o['days']}\n"
        f"Coins: {fmt_coins(o['coins'])}\n"
        f"Status: {o.get('status')}\n"
        f"Created: {o.get('created_at','N/A')}"
    )


def format_admin_payment(o):
    if not o: return "Payment not found."
    return (
        "💳 <b>Coin Payment</b>\n\n"
        f"Order: <code>{o['id']}</code>\n"
        f"User: {o.get('name','')} (@{o.get('username') or 'no_username'})\n"
        f"User ID: <code>{o['user_id']}</code>\n"
        f"Amount: ₹{o['amount']}\n"
        f"Coins: {o['coins']}\n"
        f"UTR: <code>{o['utr']}</code>\n"
        f"Status: {o.get('status')}\n"
        f"Created: {o.get('created_at','N/A')}"
    )


def user_record_from_id(user_id):
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"id": int(user_id), "name": "User", "username": "", "coins": 0.0,
                             "total_bought": 0.0, "total_earned": 0.0, "joined_at": iso_now(), "referred_by": None}
    return db["users"][uid]


async def handle_admin_text(update, context, text):
    flow = context.user_data.get("flow")

    if flow == "admin_user_id":
        if not text.isdigit():
            await update.message.reply_text("Invalid Telegram user ID."); return
        target = user_record_from_id(int(text)); context.user_data["admin_target"] = text; context.user_data["flow"] = "admin_user_balance"
        await update.message.reply_text(
            f"👤 User <code>{text}</code>\nCurrent balance: <b>{fmt_coins(target.get('coins',0))}</b>\n\nSend new balance:", parse_mode="HTML")
        return

    if flow == "admin_user_balance":
        try: amount = coins(text)
        except ValueError:
            await update.message.reply_text("Enter a valid number."); return
        target = user_record_from_id(int(context.user_data["admin_target"]))
        target["coins"] = max(0, amount); save_db(); context.user_data.clear()
        await update.message.reply_text(f"✅ Balance set to {fmt_coins(amount)} coins.", reply_markup=admin_back_kb()); return

    if flow == "admin_set_balance_order":
        try: amount = coins(text)
        except ValueError:
            await update.message.reply_text("Enter a valid number."); return
        oid = context.user_data.get("admin_order_id")
        o = next((x for x in db["coin_orders"] if x["id"] == oid), None)
        if not o: await update.message.reply_text("Order not found."); context.user_data.clear(); return
        if o.get("status") not in ("verifying", "pending", "manual_review"):
            await update.message.reply_text("Payment is no longer pending.", reply_markup=admin_back_kb()); context.user_data.clear(); return
        u = user_record_from_id(o["user_id"]); u["coins"] = coins(u.get("coins",0) + amount)
        o["status"] = "approved"; o["approved_at"] = iso_now(); o["custom_added"] = amount
        save_db(); context.user_data.clear()
        await finish_payment_wait_message(
            context, o,
            "✅ <b>Payment Approved</b>\n\n"
            f"Custom balance added: <b>{fmt_coins(amount)} coins</b>\n"
            f"New balance: <b>{fmt_coins(u['coins'])}</b>",
            main_kb(o["user_id"]),
        )
        await notify_user(context, o["user_id"], f"✅ Admin updated your balance.\n\nAdded: <b>{fmt_coins(amount)} coins</b>\nBalance: <b>{fmt_coins(u['coins'])}</b>", back_menu_kb())
        await update.message.reply_text("✅ Balance updated and payment marked approved.", reply_markup=admin_back_kb()); return

    if flow == "admin_plan_add":
        name=text.strip()
        if not name: await update.message.reply_text("Plan name cannot be empty."); return
        pid=uuid.uuid4().hex[:8]
        db["config"]["plans"][pid]={"id":pid,"name":name,"active":True,"packages":{}}
        save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Plan added.",reply_markup=admin_back_kb()); return

    if flow == "admin_plan_edit_name":
        pid=context.user_data.get("admin_plan_id"); plan=find_plan(pid)
        if not plan: context.user_data.clear(); await update.message.reply_text("Plan not found."); return
        if not text.strip(): await update.message.reply_text("Plan name cannot be empty."); return
        plan["name"]=text.strip(); save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Plan name updated.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data=f"admin_plan_view_{pid}")]])); return

    if flow == "admin_pkg_add":
        parts=[x.strip() for x in text.split("|",2)]
        if len(parts)!=3: await update.message.reply_text("Use: Button Name | Coins | Days"); return
        try: price=coins(parts[1]); days=int(parts[2])
        except ValueError: await update.message.reply_text("Coins must be a number and Days must be a whole number."); return
        if price<0 or days<1: await update.message.reply_text("Coins must be >= 0 and Days must be >= 1."); return
        pid=context.user_data.get("admin_plan_id"); plan=find_plan(pid)
        if not plan: context.user_data.clear(); await update.message.reply_text("Plan not found."); return
        pkgid=uuid.uuid4().hex[:8]
        plan.setdefault("packages",{})[pkgid]={"id":pkgid,"name":parts[0],"coins":price,"days":days,"active":True}
        save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Package added.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Packages",callback_data=f"admin_plan_packages_{pid}")]])); return

    if flow in ("admin_pkg_edit_name","admin_pkg_edit_coins","admin_pkg_edit_days"):
        pid=context.user_data.get("admin_plan_id"); pkgid=context.user_data.get("admin_package_id"); pkg=find_package(find_plan(pid),pkgid)
        if not pkg: context.user_data.clear(); await update.message.reply_text("Package not found."); return
        if flow=="admin_pkg_edit_name":
            if not text.strip(): await update.message.reply_text("Package name cannot be empty."); return
            pkg["name"]=text.strip()
        elif flow=="admin_pkg_edit_coins":
            try: pkg["coins"]=coins(text)
            except ValueError: await update.message.reply_text("Enter a valid coin amount."); return
        else:
            try: pkg["days"]=int(text)
            except ValueError: await update.message.reply_text("Enter a whole number of days."); return
            if pkg["days"]<1: await update.message.reply_text("Days must be at least 1."); return
        save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Package updated.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Package",callback_data=f"admin_pkg_view_{pid}_{pkgid}")]])); return

    if flow == "admin_price_add":
        parts=[x.strip().replace("₹","") for x in text.split("|",1)]
        if len(parts)!=2: await update.message.reply_text("Use: ₹ Amount | Coins"); return
        try: amount=int(parts[0]); coin_value=coins(parts[1])
        except ValueError: await update.message.reply_text("Amount and coins must be numeric."); return
        if amount<=0 or coin_value<0: await update.message.reply_text("Amount must be > 0 and coins must be >= 0."); return
        db["config"].setdefault("coin_pricing",[]).append({"id":uuid.uuid4().hex[:8],"amount":amount,"coins":coin_value,"active":True})
        save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Pricing added.",reply_markup=admin_back_kb()); return

    if flow in ("admin_price_edit_amount","admin_price_edit_coins"):
        pid=context.user_data.get("admin_price_id"); item=next((x for x in db["config"].get("coin_pricing",[]) if str(x.get("id"))==pid),None)
        if not item: context.user_data.clear(); await update.message.reply_text("Pricing not found."); return
        try:
            if flow=="admin_price_edit_amount":
                item["amount"]=int(text.replace("₹",""));
                if item["amount"]<=0: raise ValueError
            else: item["coins"]=coins(text)
        except ValueError: await update.message.reply_text("Enter a valid positive amount."); return
        save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Pricing updated.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Pricing",callback_data="admin_manage_pricing")]])); return

    if flow.startswith("admin_verify_edit_"):
        tid=context.user_data.get("admin_verify_id"); task=next((t for t in db["verify_tasks"] if str(t.get("id"))==tid),None)
        if not task: context.user_data.clear(); await update.message.reply_text("Verification link not found."); return
        kind=flow[len("admin_verify_edit_"):]
        if kind=="name":
            if not text.strip(): await update.message.reply_text("Name cannot be empty."); return
            task["title"]=text.strip()
        elif kind=="url":
            if not text.startswith(("http://","https://")): await update.message.reply_text("Send a valid http/https URL."); return
            task["url"]=text.strip()
        elif kind=="details": task["details"]=text.strip()
        elif kind=="code": task["code"]=text.strip().upper()
        elif kind=="reward":
            try: task["reward"]=coins(text)
            except ValueError: await update.message.reply_text("Enter a valid reward."); return
        save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Verification link updated.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Verification Link",callback_data=f"admin_verify_view_{tid}")]])); return

    if flow == "admin_code_create":
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("Use: CODE COINS"); return
        code = parts[0].upper()
        try: reward = coins(parts[1])
        except ValueError:
            await update.message.reply_text("Invalid coin reward."); return
        db["redeem_codes"][code] = {"coins": reward, "active": True, "used_by": [], "created_at": iso_now()}
        save_db(); context.user_data.clear()
        await update.message.reply_text(f"✅ Code <code>{code}</code> created for {fmt_coins(reward)} coins.", parse_mode="HTML", reply_markup=admin_back_kb()); return

    if flow == "admin_verify_add":
        parts=[x.strip() for x in text.split("|",4)]
        if len(parts)!=5 or not parts[1].startswith(("http://","https://")):
            await update.message.reply_text("Use: Name | URL | Details | CODE | Reward"); return
        try: reward=coins(parts[4])
        except ValueError: await update.message.reply_text("Invalid reward."); return
        task={"id":uuid.uuid4().hex[:8],"title":parts[0],"url":parts[1],"details":parts[2],"code":parts[3].upper(),"reward":reward,"active":True,"created_at":iso_now()}
        db["verify_tasks"].append(task); save_db(); context.user_data.clear()
        await update.message.reply_text(f"✅ Verification link added: {escape(parts[0])}",parse_mode="HTML",reply_markup=admin_back_kb()); return

    if flow == "admin_payment_settings":
        parts = [x.strip() for x in text.split("|")]
        if len(parts) < 2:
            await update.message.reply_text("Use: UPI_ID | NAME | QR_FILE_ID(optional)"); return
        db["config"]["upi_id"] = parts[0]; db["config"]["upi_name"] = parts[1]
        if len(parts) >= 3: db["config"]["payment_qr_file_id"] = parts[2]
        save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Payment settings updated.", reply_markup=admin_back_kb()); return

    if flow == "admin_howto":
        if not text.startswith(("http://", "https://")):
            await update.message.reply_text("Send a valid http/https URL."); return
        db["config"]["how_to_pay_url"] = text; save_db(); context.user_data.clear()
        await update.message.reply_text("✅ How-to-Pay link saved.", reply_markup=admin_back_kb()); return

    if flow == "admin_contact":
        db["config"]["admin_contact"] = text.lstrip("@").strip(); save_db(); context.user_data.clear()
        await update.message.reply_text("✅ Admin contact updated.", reply_markup=admin_back_kb()); return


# =============================================================================
# Daily 4 AM reminder — no Like API is used. It only reminds admin to deliver likes.
# =============================================================================
async def daily_admin_reminder(context=None):
    active = [a for a in db["autolikes"] if a.get("status") == "active"]
    if not active:
        return
    lines = ["🌅 <b>4:00 AM AutoLike Reminder</b>\n\nPending manual delivery:\n"]
    for a in active:
        lines.append(f"• UID <code>{a['uid']}</code> | {REGION_NAMES.get(a['region'],a['region'])} | {a['package_title']} | expires {a['expiry_date']}")
    text = "\n".join(lines)
    if context:
        await send_admins(context, text)
    else:
        # Job callback supplies no context in older APScheduler versions; global app is used below.
        if APP:
            for admin_id in OWNER_IDS:
                try: await APP.bot.send_message(admin_id, text=text, parse_mode="HTML")
                except Exception: pass


# =============================================================================
# Commands
# =============================================================================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to open the menu.", reply_markup=main_kb(update.effective_user.id))


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Not available."); return
    await update.message.reply_text("🔐 Admin Panel", reply_markup=admin_panel_kb())


async def post_init(application):
    global APP
    APP = application
    await application.bot.set_my_commands([
        BotCommand("start", "Open main menu"),
        BotCommand("help", "Help & Support"),
    ], scope=BotCommandScopeDefault())
    for owner_id in OWNER_IDS:
        try:
            await application.bot.set_my_commands([
                BotCommand("start", "Open main menu"),
                BotCommand("admin", "Open Admin Panel"),
            ], scope=BotCommandScopeChat(chat_id=owner_id))
        except Exception:
            pass
    for owner_id in OWNER_IDS:
        user_record_from_id(owner_id)
    save_db()
    scheduler.add_job(daily_admin_reminder, CronTrigger(hour=4, minute=0, timezone=IST), id="daily_reminder", replace_existing=True)
    scheduler.start()
    print("Bot online. No Like API is configured; AutoLike delivery is manual.")


APP = None
scheduler = AsyncIOScheduler()


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, msg_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
