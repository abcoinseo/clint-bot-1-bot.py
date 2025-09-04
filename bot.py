import logging
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "7869422405:AAGu-_GNbcfx2M22d5ZEoyZa6pmlY2XOeNk"
FIREBASE_CREDENTIALS_PATH = "fire.json"
FIREBASE_DB_URL = "https://clint-bot-101-default-rtdb.firebaseio.com/"

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- FIREBASE INIT ---
try:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    logger.info("Firebase initialized successfully ✅")
except Exception as e:
    logger.error(f"Firebase init failed ❌: {e}")
    exit()

# --- HELPERS ---
def get_user_ref(user_id: int):
    return db.reference(f"users/{user_id}")

def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Earn", callback_data="menu_earn"),
         InlineKeyboardButton("📋 Tasks", callback_data="menu_tasks")],
        [InlineKeyboardButton("👥 Referrals", callback_data="menu_referrals"),
         InlineKeyboardButton("🎁 Redeem", callback_data="menu_redeem")],
        [InlineKeyboardButton("📊 History", callback_data="menu_history"),
         InlineKeyboardButton("👤 Profile", callback_data="menu_profile")]
    ])

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_ref = get_user_ref(user_id)
    data = user_ref.get()

    if not data:
        user_ref.set({
            "id": user_id,
            "name": user.full_name,
            "username": user.username,
            "points": 0,
            "referrals": {}
        })
        msg = f"👋 Welcome {user.first_name}! You have joined EarnFlux 🚀"
    else:
        msg = f"👋 Welcome back {user.first_name}!"

    await update.message.reply_text(msg, reply_markup=menu_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Available commands:\n/start - Start bot\n/help - Show help\n/claim - Claim rewards")

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref = get_user_ref(user_id)
    data = ref.get()
    if not data:
        await update.message.reply_text("⚠️ Please use /start first.")
        return
    ref.update({"points": data.get("points", 0) + 10})
    await update.message.reply_text("🎁 You claimed 10 points!")

# --- CALLBACK HANDLER ---
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_earn":
        await query.edit_message_text("🚀 Complete tasks to earn points!", reply_markup=menu_keyboard())
    elif query.data == "menu_profile":
        user_id = query.from_user.id
        data = get_user_ref(user_id).get()
        text = f"👤 Name: {data.get('name')}\nUsername: @{data.get('username')}\nPoints: {data.get('points',0)}"
        await query.edit_message_text(text, reply_markup=menu_keyboard())
    else:
        await query.edit_message_text("📋 Coming soon!", reply_markup=menu_keyboard())

# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("claim", claim))
    app.add_handler(CallbackQueryHandler(menu_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("ℹ️ Use /help")))

    logger.info("Bot is running 🚀")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
