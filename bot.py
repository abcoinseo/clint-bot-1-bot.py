import logging
import os
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- Configuration ---
TELEGRAM_BOT_TOKEN = "7869422405:AAGu-_GNbcfx2M22d5ZEoyZa6pmlY2XOeNk"  # Your Bot Token
FIREBASE_CREDENTIALS_PATH = "fire.json"  # Path to Firebase Admin SDK JSON
FIREBASE_DB_URL = "https://clint-bot-101-default-rtdb.firebaseio.com/"  # Firebase Realtime Database URL

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Firebase Initialization ---
try:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred, {
        "databaseURL": FIREBASE_DB_URL
    })
    logger.info("Firebase initialized successfully ✅")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}")
    exit()

# --- Helper Functions ---
def generate_referral_code(user_id: int) -> str:
    return f"ref_{user_id}"

def get_user_ref(user_id: int) -> db.Reference:
    return db.reference(f"users/{user_id}")

def get_main_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🚀 Earn", callback_data="menu_earn"),
            InlineKeyboardButton("📋 Tasks", callback_data="menu_tasks"),
        ],
        [
            InlineKeyboardButton("👥 Referrals", callback_data="menu_referrals"),
            InlineKeyboardButton("🎁 Redeem", callback_data="menu_redeem"),
        ],
        [
            InlineKeyboardButton("📊 History", callback_data="menu_history"),
            InlineKeyboardButton("👤 Profile", callback_data="menu_profile"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    username = user.username
    first_name = user.first_name
    last_name = user.last_name

    # ✅ Fix: await get_profile_photos()
    photos = await user.get_profile_photos()
    photo_url = photos.photos[0][0].file_id if photos and photos.total_count > 0 else None

    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    referral_code_from_url = None
    if context.args:
        referral_code_from_url = context.args[0]

    if not user_data:
        logger.info(f"New user detected: {user_id}")
        new_user_data = {
            "id": user_id,
            "name": f"{first_name} {last_name or ''}".strip(),
            "username": username,
            "photo_url": photo_url,
            "points": 0,
            "totalEarned": 0,
            "tasksCompleted": 0,
            "referralCode": generate_referral_code(user_id),
            "referredBy": None,
            "referrals": {},
            "unclaimedBonuses": {},
            "createdAt": firebase_admin.db.SERVER_VALUE
        }
        user_ref.set(new_user_data)

        welcome_message = (
            f"👋 Welcome, {first_name}!\n\n"
            f"✅ You have successfully joined *EarnFlux*.\n\n"
            "Start earning points by completing tasks!"
        )
        await update.message.reply_text(welcome_message, reply_markup=get_main_menu_markup(), parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "👋 Welcome back to *EarnFlux*!",
            reply_markup=get_main_menu_markup(),
            parse_mode="Markdown"
        )

# --- Claim Bonuses ---
async def claim_bonuses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    if not user_data:
        await update.message.reply_text("⚠️ Error: User data not found.")
        return

    unclaimed_bonuses = user_data.get("unclaimedBonuses", {})
    total_points_to_claim = sum(bonus.get("points", 0) for bonus in unclaimed_bonuses.values())

    if total_points_to_claim == 0:
        await update.message.reply_text("ℹ️ You have no unclaimed bonuses.")
        return

    try:
        user_ref.update({
            "points": firebase_admin.db.ServerValue.increment(total_points_to_claim)
        })
        user_ref.child("unclaimedBonuses").delete()
        await update.message.reply_text(f"✅ Successfully claimed {total_points_to_claim} bonus points!")
    except Exception as e:
        logger.error(f"Error claiming bonuses: {e}")
        await update.message.reply_text("❌ Failed to claim bonuses. Please try again.")

# --- Menu Callback ---
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    if not user_data:
        await query.edit_message_text("⚠️ Error: User data not found. Please use /start again.")
        return

    callback_data = query.data
    if callback_data == "menu_earn":
        await query.edit_message_text("🚀 Complete tasks to earn points!", reply_markup=get_main_menu_markup())
    elif callback_data == "menu_tasks":
        await query.edit_message_text("📋 Task list coming soon!", reply_markup=get_main_menu_markup())
    elif callback_data == "menu_referrals":
        referrals_count = len(user_data.get("referrals", {}))
        referral_message = (
            f"👥 **Referral Program**\n\n"
            f"Your Code: `{user_data.get('referralCode')}`\n"
            f"Referrals: {referrals_count}\n"
        )
        keyboard = [[InlineKeyboardButton("🎁 Claim Bonuses", callback_data="claim_bonuses")]]
        await query.edit_message_text(referral_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif callback_data == "menu_profile":
        profile_message = (
            f"👤 **Your Profile**\n\n"
            f"Name: {user_data.get('name')}\n"
            f"Username: @{user_data.get('username')}\n"
            f"Points: {user_data.get('points', 0)}\n"
        )
        await query.edit_message_text(profile_message, reply_markup=get_main_menu_markup(), parse_mode="Markdown")

# --- Main Function ---
def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claim", claim_bonuses))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(claim_bonuses, pattern="^claim_bonuses$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("ℹ️ Use the menu or /start to navigate.")))
    logger.info("Bot is running 🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
