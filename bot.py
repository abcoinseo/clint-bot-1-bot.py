import logging
import os
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- Configuration ---
TELEGRAM_BOT_TOKEN = "7869422405:AAEa-juW9IfdJTr2zPOP5b48Np7jOP0K6lY"  # Your Bot Token
FIREBASE_CREDENTIALS_PATH = "fire.json" # Path to your Firebase Admin SDK JSON file
FIREBASE_DB_URL = "https://clint-bot-101-default-rtdb.firebaseio.com/" # Your Firebase Realtime Database URL

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Firebase Initialization ---
try:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_DB_URL
    })
    logger.info("Firebase initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}")
    exit()

# --- Helper Functions ---

def generate_referral_code(user_id: int) -> str:
    """Generates a unique referral code for a user."""
    return f"ref_{user_id}" # Simpler referral code for this example

def get_user_ref(user_id: int) -> db.Reference:
    """Gets a Firebase DB reference for a specific user."""
    return db.reference(f'users/{user_id}')

def get_referrer_by_code(referral_code: str):
    """Finds a referrer's user ID based on their referral code."""
    users_ref = db.reference('users')
    # Query for users whose referralCode matches the provided code
    # Note: Firebase RTDB queries are limited. A more efficient way for large scale
    # would be to have a separate mapping or use Firestore.
    # For this example, we'll do a query.
    # Ensure referral codes are stored directly or as a child in user data.
    # Let's assume referralCode is a direct property of the user object.
    
    # A more direct lookup if referralCode is a child:
    # users_ref = db.reference('users').orderByChild('referralCode').equalTo(referral_code)
    # For simplicity in this example, we'll assume the referral code is just the user ID prefixed.
    # e.g. if user_id is 12345, referral_code is "ref_12345"
    try:
        referrer_id_str = referral_code.replace("ref_", "")
        referrer_id = int(referrer_id_str)
        user_data = get_user_ref(referrer_id).get()
        if user_data and user_data.get('referralCode') == referral_code:
            return referrer_id, user_data
    except ValueError:
        logger.warning(f"Invalid referrer code format: {referral_code}")
    except Exception as e:
        logger.error(f"Error finding referrer for code {referral_code}: {e}")
    return None, None

async def start(update: Update, context: object) -> None:
    """Handles the /start command, including referral logic."""
    user = update.effective_user
    user_id = user.id
    username = user.username
    first_name = user.first_name
    last_name = user.last_name
    photo_url = user.get_profile_photos().photos[0][0].file_id if user.get_profile_photos() else None # Get profile pic if available

    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    referral_code_from_url = None
    if context.args:
        referral_code_from_url = context.args[0]
        logger.info(f"User {user_id} started with referral code: {referral_code_from_url}")

    if not user_data:
        logger.info(f"New user detected: {user_id}")
        
        # Check if referral code is provided in start command
        referrer_id = None
        referrer_info = None
        if referral_code_from_url:
            found_referrer_id, found_referrer_info = await get_referrer_by_code(referral_code_from_url)
            if found_referrer_id and found_referrer_id != user_id: # Prevent self-referral
                referrer_id = found_referrer_id
                referrer_info = found_referrer_info
                logger.info(f"User {user_id} is referred by {referrer_id}")

        new_user_data = {
            "id": user_id,
            "name": f"{first_name} {last_name or ''}".strip(),
            "username": username,
            "photo_url": photo_url,
            "points": 0,
            "totalEarned": 0,
            "tasksCompleted": 0,
            "referralCode": generate_referral_code(user_id),
            "referredBy": referrer_id,
            "referredByName": referrer_info.get("name") if referrer_info else None,
            "referrals": {}, # Dictionary to store referred users: {ref_user_id: {name, username, joinedAt, totalEarned}}
            "unclaimedBonuses": {}, # Dictionary for unclaimed referral bonuses
            "createdAt": firebase_admin.db.SERVER_VALUE
        }
        user_ref.set(new_user_data)
        
        # If referred, add to referrer's list
        if referrer_id and referrer_info:
            try:
                referrer_ref = get_user_ref(referrer_id)
                # Ensure referrals dictionary exists
                referrer_data_snapshot = referrer_ref.get()
                if referrer_data_snapshot is None:
                    logger.error(f"Referrer data for ID {referrer_id} not found.")
                    return

                referrals_dict = referrer_data_snapshot.get('referrals', {})
                referrals_dict[str(user_id)] = {
                    "name": new_user_data["name"],
                    "username": username,
                    "joinedAt": firebase_admin.db.SERVER_VALUE,
                    "totalEarned": 0 # Initialize referral earning for this user
                }
                referrer_ref.update({"referrals": referrals_dict})
                logger.info(f"Added user {user_id} to referrer {referrer_id}'s referrals list.")
                
                # Send a welcome message to the referrer (optional)
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 New referral! {new_user_data['name']} ({username}) has joined EarnFlux via your link!"
                    )
                except Exception as e:
                    logger.warning(f"Could not send welcome message to referrer {referrer_id}: {e}")

            except Exception as e:
                logger.error(f"Error updating referrer's referral list for user {user_id}: {e}")
        
        welcome_message = f"👋 Welcome, {first_name}! You've successfully joined EarnFlux. Start earning points by completing tasks."
        if referrer_info:
            welcome_message += f"\nYou were referred by {referrer_info.get('name')}!"
        welcome_message += "\n\nUse the buttons below to navigate."
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=get_main_menu_markup()
        )
    else:
        logger.info(f"Existing user logged in: {user_id}")
        await update.message.reply_text(
            "👋 Welcome back to EarnFlux!",
            reply_markup=get_main_menu_markup()
        )

async def get_referrer_by_code_for_app(referral_code: str):
    """
    Helper to find referrer for app, assuming code is just user ID.
    In a real app, you'd map codes to user IDs more robustly.
    """
    try:
        referrer_id_str = referral_code.replace("ref_", "")
        referrer_id = int(referrer_id_str)
        
        # Directly check if the user exists and has this referral code
        # This query might be slow if you have many users and no proper indexing.
        # If referralCode is a direct child of user object:
        user_ref = db.reference(f'users/{referrer_id}')
        user_data = user_ref.get()
        
        if user_data and user_data.get('referralCode') == referral_code:
            return referrer_id, user_data
    except ValueError:
        logger.warning(f"Invalid referrer code format provided to app: {referral_code}")
    except Exception as e:
        logger.error(f"Error finding referrer for code {referral_code} from app: {e}")
    return None, None

# --- Task Completion and Reward Logic ---

async def complete_task_reward(context: object, user_id: int, task_id: str, task_points: int, task_title: str) -> None:
    """Handles rewarding a user for task completion and referral bonuses."""
    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()
    
    if not user_data:
        logger.error(f"User {user_id} not found for task completion reward.")
        return

    # --- Update User's Points and Stats ---
    try:
        new_points = user_data.get('points', 0) + task_points
        new_total_earned = user_data.get('totalEarned', 0) + task_points
        new_tasks_completed = user_data.get('tasksCompleted', 0) + 1
        
        user_ref.update({
            "points": new_points,
            "totalEarned": new_total_earned,
            "tasksCompleted": new_tasks_completed
        })
        logger.info(f"Rewarded user {user_id} with {task_points} points for task '{task_title}'.")

        # --- Handle Referral Bonus ---
        referrer_id = user_data.get('referredBy')
        referrer_name = user_data.get('referredByName')
        
        if referrer_id and referrer_name:
            referral_bonus_percentage = 0.10 # 10%
            bonus_points = int(task_points * referral_bonus_percentage)
            
            if bonus_points > 0:
                referrer_user_ref = get_user_ref(referrer_id)
                referrer_user_data = referrer_user_ref.get()

                if referrer_user_data:
                    # Add bonus to referrer's unclaimed bonuses
                    unclaimed_bonuses = referrer_user_data.get('unclaimedBonuses', {})
                    bonus_key = f"bonus_{user_id}_{task_id}" # Simple key to avoid duplicates if needed
                    unclaimed_bonuses[bonus_key] = {
                        "fromUserId": user_id,
                        "fromName": user_data.get('name', 'User'),
                        "points": bonus_points,
                        "type": "task_bonus",
                        "taskTitle": task_title,
                        "timestamp": firebase_admin.db.SERVER_VALUE
                    }
                    referrer_user_ref.update({"unclaimedBonuses": unclaimed_bonuses})
                    
                    # Update totalEarned for this specific referral relationship
                    referrals_data = referrer_user_data.get('referrals', {})
                    if str(user_id) in referrals_data:
                        referrals_data[str(user_id)]['totalEarned'] = firebase_admin.db.ServerValue.increment(bonus_points)
                        referrer_user_ref.update({"referrals": referrals_data})
                    
                    logger.log(logging.INFO, f"Awarded {bonus_points} referral bonus to {referrer_id} from {user_id} for task '{task_title}'.")
                else:
                    logger.warning(f"Referrer {referrer_id} data not found for bonus calculation.")

        # --- Add to Task History ---
        task_history_ref = db.reference(f'taskHistory/{user_id}').push()
        task_history_ref.set({
            "taskId": task_id,
            "taskTitle": task_title,
            "pointsEarned": task_points,
            "completedAt": firebase_admin.db.SERVER_VALUE
        })
        logger.info(f"Added task completion to history for user {user_id}, task {task_id}.")

    except Exception as e:
        logger.error(f"Error processing reward for user {user_id}, task {task_id}: {e}")
        # Consider sending an error message to the user or admin


async def claim_bonuses(update: Update, context: object) -> None:
    """Handles claiming all unclaimed referral bonuses for a user."""
    user = update.effective_user
    user_id = user.id
    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    if not user_data:
        await update.message.reply_text("Error: User data not found.")
        return

    unclaimed_bonuses = user_data.get("unclaimedBonuses", {})
    total_points_to_claim = sum(bonus.get("points", 0) for bonus in unclaimed_bonuses.values())

    if total_points_to_claim == 0:
        await update.message.reply_text("You have no unclaimed bonuses.")
        return

    try:
        # Update user points
        user_ref.update({
            "points": firebase_admin.db.ServerValue.increment(total_points_to_claim)
        })
        # Clear unclaimed bonuses
        user_ref.child("unclaimedBonuses").remove()
        
        await update.message.reply_text(f"✅ Successfully claimed {total_points_to_claim} bonus points!")
        logger.info(f"User {user_id} claimed {total_points_to_claim} unclaimed bonuses.")

    except Exception as e:
        logger.error(f"Error claiming bonuses for user {user_id}: {e}")
        await update.message.reply_text("Failed to claim bonuses. Please try again.")

# --- Menu and Command Handlers ---

def get_main_menu_markup() -> InlineKeyboardMarkup:
    """Returns the inline keyboard markup for the main menu."""
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

async def menu_callback(update: Update, context: object) -> None:
    """Handles callback queries for menu navigation."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback

    user_id = query.from_user.id
    user_ref = get_user_ref(user_id)
    user_data = user_ref.get()

    if not user_data:
        await query.edit_message_text("Error: User data not found. Please restart the bot using /start.")
        return

    callback_data = query.data
    
    # --- Navigation ---
    if callback_data == "menu_earn":
        await query.edit_message_text(
            "Welcome to the Earn section! Complete tasks to earn points.",
            reply_markup=get_main_menu_markup()
        )
    elif callback_data == "menu_tasks":
        # In a real bot, you'd show available tasks here. For simplicity, we'll just
        # show a placeholder message and link to the web app.
        web_app_info = query.message.reply_markup.inline_keyboard[0][0].web_app # Assuming 'Earn' button is first
        
        # Fallback for when web_app_info might not be directly accessible this way
        # In a real bot, you'd likely have a command to open the web app.
        # For this example, we'll assume the web app is opened via a button in the main menu.
        await query.edit_message_text(
            "Browse and complete various tasks in our Web App to earn points!\n\n"
            "Click the 'Earn' button in the main menu to open the app.",
            reply_markup=get_main_menu_markup()
        )
    elif callback_data == "menu_referrals":
        referrals_count = len(user_data.get("referrals", {}))
        earned_from_referrals = sum(ref.get("totalEarned", 0) for ref in user_data.get("referrals", {}).values())
        unclaimed_bonus_points = sum(bonus.get("points", 0) for bonus in user_data.get("unclaimedBonuses", {}).values())

        referral_message = (
            f"👥 **Referral Program**\n\n"
            f"Your Referral Code: `{user_data.get('referralCode', 'N/A')}`\n"
            f"You have successfully referred: *{referrals_count}* users.\n"
            f"Earned from referrals: *{earned_from_referrals}* points.\n"
            f"Unclaimed bonuses: *{unclaimed_bonus_points}* points.\n\n"
            f"Share your code with friends to earn rewards!"
        )
        
        keyboard = [
            [InlineKeyboardButton("Claim All Bonuses", callback_data="claim_bonuses")],
            [InlineKeyboardButton("Back to Menu", callback_data="menu_earn")]
        ]
        await query.edit_message_text(
            referral_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    elif callback_data == "menu_redeem":
        await query.edit_message_text(
            "Browse and redeem rewards in our Web App.\n\n"
            "Click the 'Earn' button in the main menu to open the app.",
            reply_markup=get_main_menu_markup()
        )
    elif callback_data == "menu_history":
        await query.edit_message_text(
            "View your transaction history in our Web App.\n\n"
            "Click the 'Earn' button in the main menu to open the app.",
            reply_markup=get_main_menu_markup()
        )
    elif callback_data == "menu_profile":
        profile_message = (
            f"👤 **Your Profile**\n\n"
            f"Name: {user_data.get('name', 'N/A')}\n"
            f"Username: @{user_data.get('username', 'N/A')}\n"
            f"Points Balance: *{user_data.get('points', 0)}*\n"
            f"Tasks Completed: *{user_data.get('tasksCompleted', 0)}*\n"
        )
        if user_data.get('referredBy'):
            profile_message += f"Referred by: {user_data.get('referredByName', 'N/A')}\n"

        await query.edit_message_text(
            profile_message,
            reply_markup=get_main_menu_markup(),
            parse_mode='Markdown'
        )

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start)) # Alias for /start
    application.add_handler(CommandHandler("claim", claim_bonuses)) # Command to claim bonuses

    # --- Callback Query Handler for Menu ---
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(claim_bonuses, pattern="^claim_bonuses$"))

    # --- Message Handler (for general messages, or to redirect if needed) ---
    # Handle text messages that are not commands
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Use the menu or /start to navigate.")))

    # Start the Bot
    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
