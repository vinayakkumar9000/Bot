import asyncio
import logging
import requests
import uuid
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAILTM_DOMAIN = "https://api.mail.tm"
user_sessions = {}
user_stats = {}
user_favorites = {}
user_expiry = {}

# --- Helper Functions ---

def fetch_domains():
    try:
        res = requests.get(f"{MAILTM_DOMAIN}/domains")
        if res.status_code == 200:
            return [d["domain"] for d in res.json()["hydra:member"]]
    except Exception as e:
        logger.error(f"Domain fetch error: {e}")
    return []

def generate_username():
    names = ["Aanya", "Meera", "Saanvi", "Anika", "Diya", "Kiara", "Zara", "Sophia", "Emma", "Olivia",
             "Ava", "Lily", "Mila", "Nora", "Ella", "Isha", "Tara", "Riya", "Anaya", "Myra", "Neha",
             "Shruti", "Kavya", "Radhika", "Simran", "Ira", "Aarohi", "Ishita", "Avni", "Navya"]
    return f"{random.choice(names).lower()}{random.randint(1000,9999)}"

def generate_email_address(username):
    domains = fetch_domains()
    if not domains:
        raise Exception("⚠️ No domains found. Try again later.")
    return f"{username}@{random.choice(domains)}"

def create_temp_account(email, password):
    res = requests.post(f"{MAILTM_DOMAIN}/accounts", json={"address": email, "password": password})
    if res.status_code == 201:
        token_res = requests.post(f"{MAILTM_DOMAIN}/token", json={"address": email, "password": password})
        if token_res.status_code == 200:
            return token_res.json().get("token")
    raise Exception("⚠️ Email creation failed. Try again.")

def get_inbox(token):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{MAILTM_DOMAIN}/messages", headers=headers)
    if res.status_code == 200:
        return res.json()["hydra:member"]
    return []

# --- UI Builders ---

def build_main_menu(user_id):
    session = user_sessions.get(user_id)
    stats = user_stats.get(user_id, {"created": 0, "received": 0})
    text = ""
    buttons = []

    if session:
        email = session["email"]
        messages = get_inbox(session["token"])
        stats["received"] = len(messages)
        text += (
            f"📧 *Your Email:* `{email}`\n"
            f"📬 *Received:* {stats['received']} messages\n"
        )
        buttons.append([InlineKeyboardButton("🔄 Generate New Email", callback_data="create_mail")])
        buttons.append([InlineKeyboardButton("📥 Check Inbox", callback_data="check_inbox")])
        buttons.append([InlineKeyboardButton("📋 Copy Email", callback_data="copy_email")])
        buttons.append([InlineKeyboardButton("⭐ Save Favorite", callback_data="save_favorite")])
        buttons.append([InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu")])
    else:
        text += "👋 *Welcome to TempMail Bot!*\n\nCreate, view and manage your temporary emails easily."
        buttons.append([InlineKeyboardButton("📨 Create Temp Mail", callback_data="create_mail")])

    buttons.append([InlineKeyboardButton("📊 My Stats", callback_data="show_stats")])
    return text, InlineKeyboardMarkup(buttons)

def build_settings_menu():
    buttons = [
        [InlineKeyboardButton("✏️ Custom Username", callback_data="custom_username")],
        [InlineKeyboardButton("⏳ Set Expiry Time", callback_data="set_expiry")],
        [InlineKeyboardButton("❌ Delete Current Email", callback_data="delete_email")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")]])

def email_options():
    return [
        [InlineKeyboardButton("📋 Copy", callback_data="copy_email"),
         InlineKeyboardButton("⭐ Save", callback_data="save_favorite")],
        [InlineKeyboardButton("📥 Inbox", callback_data="check_inbox")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")]
    ]

# --- Telegram Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, keyboard = build_main_menu(user_id)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "back_to_menu":
        text, keyboard = build_main_menu(user_id)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    if query.data == "create_mail":
        try:
            username = generate_username()
            email = generate_email_address(username)
            password = str(uuid.uuid4())
            token = create_temp_account(email, password)
            user_sessions[user_id] = {"email": email, "password": password, "token": token}
            user_stats.setdefault(user_id, {"created": 0, "received": 0})
            user_stats[user_id]["created"] += 1
            await query.edit_message_text(
                f"✅ *New Temp Mail:*\n`{email}`",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(email_options())
            )
        except Exception as e:
            await query.edit_message_text(str(e), reply_markup=back_button())
        return

    if query.data == "check_inbox":
        session = user_sessions.get(user_id)
        if not session:
            await query.edit_message_text("❌ No email session found.", reply_markup=back_button())
            return

        messages = get_inbox(session["token"])
        user_stats[user_id]["received"] = len(messages)

        if not messages:
            await query.edit_message_text("📭 No messages yet.", reply_markup=back_button())
            return

        msg_list = ""
        for msg in messages[:5]:
            msg_list += f"✉️ *{msg['subject']}*\n🕒 {msg['createdAt'][:19]}\n"
            if msg.get('intro'):
                msg_list += f"{msg['intro']}\n"
            if msg.get('attachments'):
                for att in msg['attachments']:
                    msg_list += f"📎 Attachment: {att['filename']}\n"
            msg_list += "\n"

        await query.edit_message_text(
            f"📥 *Inbox Preview:*\n\n{msg_list}", parse_mode="Markdown", reply_markup=back_button()
        )
        return

    if query.data == "copy_email":
        session = user_sessions.get(user_id)
        if session:
            await query.edit_message_text(
                f"📋 *Copied Email:*\n`{session['email']}`", parse_mode="Markdown", reply_markup=back_button()
            )
        else:
            await query.edit_message_text("⚠️ No active email to copy.", reply_markup=back_button())

    if query.data == "save_favorite":
        session = user_sessions.get(user_id)
        if session:
            user_favorites[user_id] = session
            await query.edit_message_text("⭐ Email saved as favorite!", reply_markup=back_button())
        else:
            await query.edit_message_text("⚠️ No active email to save.", reply_markup=back_button())

    if query.data == "settings_menu":
        await query.edit_message_text("⚙️ Settings Menu:", reply_markup=build_settings_menu())

    if query.data == "delete_email":
        user_sessions.pop(user_id, None)
        await query.edit_message_text("❌ Your current temp mail has been deleted.", reply_markup=back_button())

    if query.data == "show_stats":
        stats = user_stats.get(user_id, {"created": 0, "received": 0})
        await query.edit_message_text(
            f"📊 *Your Stats:*\n\n🆕 Created: {stats['created']}\n📨 Received: {stats['received']}",
            parse_mode="Markdown", reply_markup=back_button()
        )

    if query.data == "custom_username":
        context.user_data["awaiting_custom_username"] = True
        await query.edit_message_text("✏️ Send me the username you want to use:", reply_markup=back_button())

    if query.data == "set_expiry":
        buttons = [
            [InlineKeyboardButton("5 min", callback_data="expiry_5"),
             InlineKeyboardButton("10 min", callback_data="expiry_10")],
            [InlineKeyboardButton("30 min", callback_data="expiry_30"),
             InlineKeyboardButton("Never", callback_data="expiry_0")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")]
        ]
        await query.edit_message_text("⏳ Choose expiry time:", reply_markup=InlineKeyboardMarkup(buttons))

    if query.data.startswith("expiry_"):
        minutes = int(query.data.split("_")[1])
        if minutes:
            user_expiry[user_id] = minutes * 60
            await query.edit_message_text(f"⏰ Email will expire in {minutes} minutes.", reply_markup=back_button())
        else:
            user_expiry[user_id] = 0
            await query.edit_message_text("♾️ Email will not expire.", reply_markup=back_button())

async def custom_username_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get("awaiting_custom_username"):
        username = update.message.text.strip().lower()
        try:
            email = generate_email_address(username)
            password = str(uuid.uuid4())
            token = create_temp_account(email, password)
            user_sessions[user_id] = {"email": email, "password": password, "token": token}
            user_stats.setdefault(user_id, {"created": 0, "received": 0})
            user_stats[user_id]["created"] += 1
            await update.message.reply_text(
                f"✅ *New Temp Mail:*\n`{email}`", parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(email_options())
            )
        except Exception as e:
            await update.message.reply_text(str(e), reply_markup=back_button())
        context.user_data["awaiting_custom_username"] = False

# --- Main Execution ---

if __name__ == "__main__":
    app = ApplicationBuilder().token("TELEGRAM_BOT_TOKEN").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_username_handler))
    print("🤖 Bot is running...")
    app.run_polling()
