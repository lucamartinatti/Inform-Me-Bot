from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ConversationHandler,
    ContextTypes,
)

from src.constants import TOPIC, LOCATIONS, LANGUAGES, AUTOMATIC, LOCATION, LANGUAGE

from src.db_tools import (
    get_user_preferences,
    save_user_preferences,
    update_automatic_status,
)
from src.logic import process_and_send_news
from src.db_tools import get_users_with_automatic_updates


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask for topic."""
    user = update.effective_user

    # Check if user has saved preferences
    preferences = get_user_preferences(user.id)

    if preferences:
        keyboard = [
            [InlineKeyboardButton("Use saved preferences", callback_data="use_saved")],
            [InlineKeyboardButton("Update preferences", callback_data="update_prefs")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"👋 Welcome back, {user.first_name}!\n\n"
            f"Your saved preferences:\n"
            f"📌 Topic: *{preferences['topic']}*\n"
            f"🌍 Location: {preferences['location']}\n"
            f"🗣️ Language: {preferences['language']}\n"
            f"🔔 Auto updates: {'Enabled' if preferences['automatic'] else 'Disabled'}\n\n"
            "What would you like to do?",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        # Don't end conversation, wait for callback
        return TOPIC

    await update.message.reply_text(
        "👋 Welcome to News Clustering Bot!\n\n"
        "I'll help you find and cluster similar news articles.\n\n"
        "What topic would you like to search for?\n"
        "(e.g., 'artificial intelligence', 'climate change', 'sports')\n\n"
        "Send /cancel to stop."
    )
    return TOPIC


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    preferences = get_user_preferences(user.id)

    if query.data == "use_saved" and preferences:
        await query.edit_message_text("🔄 Fetching news with your saved preferences...")
        await process_and_send_news(
            context,
            user.id,
            preferences["topic"],
            preferences["location"],
            preferences["language"],
        )
        await context.bot.send_message(
            chat_id=user.id,
            text="✨ Done! Send /start to search again or /settings to manage preferences.",
        )
        return ConversationHandler.END

    elif query.data == "update_prefs":
        await query.edit_message_text(
            "What topic would you like to search for?\n"
            "(e.g., 'artificial intelligence', 'climate change', 'sports')\n\n"
            "Send /cancel to stop."
        )
        return TOPIC

    return ConversationHandler.END


async def topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store topic and ask for location."""
    # Handle both regular messages and callback queries
    if update.message:
        message = update.message
        context.user_data["topic"] = message.text
    else:
        # This shouldn't happen but handle it gracefully
        return TOPIC

    keyboard = [[loc_name] for loc_name in LOCATIONS.values()]
    keyboard.append(["Skip (use US)"])
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await message.reply_text(
        f"Great! Topic: *{context.user_data['topic']}*\n\n"
        "Now, select your preferred location:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    return LOCATION


async def location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store location and ask for language."""
    user_choice = update.message.text

    if user_choice == "Skip (use US)":
        context.user_data["location"] = "US"
        context.user_data["location_name"] = "United States"
    else:
        for code, name in LOCATIONS.items():
            if name == user_choice:
                context.user_data["location"] = code
                context.user_data["location_name"] = name
                break

    keyboard = [[lang_name] for lang_name in LANGUAGES.values()]
    keyboard.append(["Skip (use English)"])
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(
        f"Location: *{context.user_data['location_name']}*\n\n"
        "Select your preferred language:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    return LANGUAGE


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store language and ask about automatic updates."""
    user_choice = update.message.text

    if user_choice == "Skip (use English)":
        context.user_data["language"] = "en"
        context.user_data["language_name"] = "English"
    else:
        for code, name in LANGUAGES.items():
            if name == user_choice:
                context.user_data["language"] = code
                context.user_data["language_name"] = name
                break

    keyboard = [["Yes, send daily updates"], ["No, just this once"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(
        f"Language: *{context.user_data['language_name']}*\n\n"
        "Would you like to receive automatic daily updates at 7:00 AM?",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    return AUTOMATIC


async def automatic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store automatic preference and process the request."""
    user = update.effective_user
    user_choice = update.message.text

    automatic = user_choice == "Yes, send daily updates"
    context.user_data["automatic"] = automatic

    # Save user data to database
    user_data = {
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "full_name": user.full_name or "",
        "username": user.username or "",
        "link": f"tg://user?id={user.id}",
    }

    preferences = {
        "topic": context.user_data["topic"],
        "language": context.user_data["language"],
        "location": context.user_data["location"],
        "automatic": automatic,
    }

    save_user_preferences(user.id, user_data, preferences)

    await update.message.reply_text(
        f"✅ Preferences saved!\n"
        f"{'🔔 You will receive daily updates at 7:00 AM.' if automatic else ''}\n\n"
        "🔄 Fetching and analyzing news...",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Fetch and send news
    await process_and_send_news(
        context,
        user.id,
        preferences["topic"],
        preferences["location"],
        preferences["language"],
    )

    await update.message.reply_text(
        "✨ Analysis complete!\n\n"
        "Commands:\n"
        "/start - New search\n"
        "/settings - Manage preferences"
    )

    return ConversationHandler.END


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user settings."""
    user = update.effective_user
    preferences = get_user_preferences(user.id)

    if not preferences:
        await update.message.reply_text(
            "You don't have saved preferences yet.\n" "Send /start to set them up!"
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                (
                    "🔔 Disable auto updates"
                    if preferences["automatic"]
                    else "🔕 Enable auto updates"
                ),
                callback_data="toggle_auto",
            )
        ],
        [InlineKeyboardButton("📝 Update preferences", callback_data="update_prefs")],
        [InlineKeyboardButton("🔄 Get news now", callback_data="use_saved")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"⚙️ Your Settings:\n\n"
        f"📌 Topic: *{preferences['topic']}*\n"
        f"🌍 Location: {preferences['location']}\n"
        f"🗣️ Language: {preferences['language']}\n"
        f"🔔 Auto updates: {'Enabled' if preferences['automatic'] else 'Disabled'}",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def toggle_automatic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle automatic updates."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    preferences = get_user_preferences(user.id)

    if preferences:
        new_status = not preferences["automatic"]
        update_automatic_status(user.id, new_status)

        await query.edit_message_text(
            f"✅ Automatic updates {'enabled' if new_status else 'disabled'}!\n\n"
            f"{'You will receive daily news at 7:00 AM.' if new_status else 'You will not receive automatic updates.'}\n\n"
            "Use /settings to change preferences."
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text(
        "Operation cancelled. Send /start to begin again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def send_daily_updates(context: ContextTypes.DEFAULT_TYPE):
    """Send daily updates to all users with automatic updates enabled."""
    # logger.info("Starting daily news updates...")

    users = get_users_with_automatic_updates()
    # logger.info(f"Sending updates to {len(users)} users")

    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["id"],
                text=f"🌅 Good morning! Here's your daily news about *{user['topic']}*",
                parse_mode="Markdown",
            )

            await process_and_send_news(
                context, user["id"], user["topic"], user["location"], user["language"]
            )

        except Exception as e:
            # logger.error(f"Failed to send update to user {user['id']}: {e}")
            print(f"Failed to send update to user {user['id']}: {e}")
