import logging
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- Configuration ---
TELEGRAM_BOT_TOKEN = "7869422405:AAGu-_GNbcfx2M22d5ZEoyZa6pmlY2XOeNk"  # Your Bot Token
FIREBASE_CREDENTIALS_PATH = "fire.json"  # Path to Firebase Admin SDK JSON file
FIREBASE_DB_URL = "https://clint-bot-101-default-rtdb.firebaseio.com/"  # Firebase DB URL

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Firebase Initialization ---
try:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    logger.info("✅ Firebase initialized successfully.")
except Exception as e:
    logger.error(f"❌ Firebase init error: {e}")
    exit()

# --- Helper Functions ---
def generate_referral_code(user_id: int) -> str:
    return f"ref_{user_id}"

def get_user_ref(user_id: int):
    return db.reference(f"users/{user_id}")

def get_referrer_by_code(referral_code: str):
    try:
        referrer_id = int(referral_code.replace("ref_", ""))
        user_data = get_user_ref(referrer_id).get()
        if user_data and user_data.get("referralCode") == referral_code:
            return referrer_id, user_data
    except Exception as e:
        logger.warning(f"Invalid referral code {referral_code}: {e}")
    return None, None

def get_main_menu_markup():
    keyboard = [
        [InlineKeyboardButton("🚀 Earn", callback_data="menu_earn"),
         InlineKeyboardButton("📋 Tasks", callback_data="menu_tasks")],
        [InlineKeyboardButton("👥 Referrals", callback_data="menu_referrals"),
         InlineKeyboardButton("🎁 Redeem", callback_data="menu_redeem")],
        [InlineKeyboardButton("📊 History", callback_data="menu_history"),
         InlineKeyboardButton("👤 Profile", callback_data="menu_profile")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id, username, first_name, last_name = user.id, user.username, user.first_name, user.last_name
    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    referral_code_from_url = context.args[0] if context.args else None

    if not user_data:
        logger.info(f"🆕 New user {user_id}")
        referrer_id, referrer_info = None, None

        if referral_code_from_url:
            found_id, found_info = get_referrer_by_code(referral_code_from_url)
            if found_id and found_id != user_id:
                referrer_id, referrer_info = found_id, found_info

        new_user_data = {
            "id": user_id,
            "name": f"{first_name} {last_name or ''}".strip(),
            "username": username,
            "points": 0,
            "totalEarned": 0,
            "tasksCompleted": 0,
            "referralCode": generate_referral_code(user_id),
            "referredBy": referrer_id,
            "referredByName": referrer_info.get("name") if referrer_info else None,
            "referrals": {},
            "unclaimedBonuses": {},
            "createdAt": db.SERVER_VALUE
        }
        user_ref.set(new_user_data)

        if referrer_id:
            referrer_ref = get_user_ref(referrer_id)
            ref_data = referrer_ref.get() or {}
            referrals = ref_data.get("referrals", {})
            referrals[str(user_id)] = {
                "name": new_user_data["name"],
                "username": username,
                "joinedAt": db.SERVER_VALUE,
                "totalEarned": 0
            }
            referrer_ref.update({"referrals": referrals})
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 New referral! {new_user_data['name']} (@{username}) joined via your link!"
                )
            except Exception as e:
                logger.warning(f"Referrer message failed: {e}")

        welcome_msg = (
            f"👋 Welcome, *{first_name}*!\n\n"
            "🔥 You have successfully joined *EarnFlux*.\n"
            "🚀 Start completing tasks and invite friends to earn more rewards.\n\n"
            "👉 Use the menu below to explore."
        )
        if referrer_info:
            welcome_msg += f"\n\n🙌 You were referred by *{referrer_info.get('name')}*."

        await update.message.reply_text(welcome_msg, reply_markup=get_main_menu_markup(), parse_mode="Markdown")

    else:
        await update.message.reply_text(
            "👋 Welcome back to *EarnFlux*!",
            reply_markup=get_main_menu_markup(),
            parse_mode="Markdown"
        )

# --- Claim Bonuses ---
async def claim_bonuses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    if not user_data:
        await update.message.reply_text("❌ Error: User not found.")
        return

    unclaimed = user_data.get("unclaimedBonuses", {})
    total_points = sum(b.get("points", 0) for b in unclaimed.values())

    if total_points == 0:
        await update.message.reply_text("ℹ️ You have no unclaimed bonuses.")
        return

    user_ref.update({"points": db.ServerValue.increment(total_points)})
    user_ref.child("unclaimedBonuses").delete()
    await update.message.reply_text(f"✅ You claimed *{total_points}* bonus points!", parse_mode="Markdown")

# --- Menu Navigation ---
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user_ref(user_id).get()

    if not user_data:
        await query.edit_message_text("❌ User not found. Use /start again.")
        return

    cb = query.data
    if cb == "menu_earn":
        await query.edit_message_text("🚀 Complete tasks to earn points!", reply_markup=get_main_menu_markup())
    elif cb == "menu_referrals":
        referrals_count = len(user_data.get("referrals", {}))
        earned = sum(r.get("totalEarned", 0) for r in user_data.get("referrals", {}).values())
        unclaimed = sum(b.get("points", 0) for b in user_data.get("unclaimedBonuses", {}).values())
        msg = (
            f"👥 *Referral Program*\n\n"
            f"🔑 Code: `{user_data['referralCode']}`\n"
            f"👤 Referred Users: *{referrals_count}*\n"
            f"💰 Earned: *{earned}* points\n"
            f"🎁 Unclaimed Bonuses: *{unclaimed}* points"
        )
        keyboard = [[InlineKeyboardButton("🎁 Claim Bonuses", callback_data="claim_bonuses")],
                    [InlineKeyboardButton("⬅ Back", callback_data="menu_earn")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif cb == "claim_bonuses":
        fake_update = Update(update.update_id, message=query.message)
        fake_update.effective_user = query.from_user
        await claim_bonuses(fake_update, context)

# --- Main ---
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claim", claim_bonuses))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^claim_bonuses$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("ℹ️ Use the menu or /start.")))
    logger.info("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
