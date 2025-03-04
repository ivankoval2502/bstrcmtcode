import asyncio
import datetime
import logging
import re
import os

from notion_client import AsyncClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)

# Настройка логирования


def create_notion_client(NOTION_TOKEN):
    return AsyncClient(auth=NOTION_TOKEN)

async def fetch_recent_posts(query: str, notion, NOTION_TECHNICAL_ISSUES_DB):
    """
    Ищет записи в Notion за последние 7 дней, содержащие ключевые слова в Title (тип Text)
    или в Username (тип Title).
    """
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
    response = await notion.databases.query(
        database_id=NOTION_TECHNICAL_ISSUES_DB,
        filter={
            "and": [
                {"property": "Date", "date": {"after": since}},
                {
                    "or": [
                        {"property": "Title", "rich_text": {"contains": query}},
                        {"property": "Username", "title": {"contains": query}}
                    ]
                }
            ]
        },
    )
    return response.get("results", [])

async def update_post_status(notion, page_id: str, new_status: str):
    """Обновляет статус выбранного поста (поле Status типа Status)."""
    try:
        response = await notion.pages.update(
            page_id=page_id,
            properties={"Status": {"status": {"name": new_status}}}
        )
        return f"Статус записи {page_id} изменён на {new_status}" if response.get("object") == "page" else "Не удалось обновить статус."
    except Exception as e:
        return f"Произошла ошибка при обновлении статуса: {e}"

async def update_post_email(notion, page_id: str, new_email: str):
    """Обновляет email выбранного поста (поле Email типа Email)."""
    try:
        response = await notion.pages.update(
            page_id=page_id,
            properties={"Email": {"email": new_email}},
        )
        return f"Email записи {page_id} изменён на {new_email}" if response.get("object") == "page" else "Не удалось обновить email."
    except Exception as e:
        return f"Произошла ошибка при обновлении email: {e}"

# --- Новые функции для изменения флажка ---

async def handle_change_flair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает команду /changeflair.
    Ищет посты по ключевому слову (в Title или Username) за последние 7 дней и предлагает список найденных записей.
    При выборе записи (callback_data вида "cfp_<page_id>") пользователь перейдет к выбору нового флажка.
    """
    query = " ".join(context.args)
    notion_inst = context.bot_data["notion"]
    NOTION_TECHNICAL_ISSUES_DB = context.bot_data["NOTION_TECHNICAL_ISSUES_DB"]
    posts = await fetch_recent_posts(query, notion_inst, NOTION_TECHNICAL_ISSUES_DB)
    if not posts:
        await update.message.reply_text("Записи не найдены.")
        return
    keyboard = [
        [InlineKeyboardButton(
            post["properties"].get("Title", {}).get("rich_text", [{}])[0]
                .get("text", {}).get("content", "(Без названия)"),
            callback_data=f"cfp_{post['id']}"
        )]
        for post in posts
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите запись для изменения флажка:", reply_markup=reply_markup)

async def update_post_flair(notion, page_id: str, new_flair: str):
    """Обновляет флажок (Post Flair) выбранного поста."""
    try:
        response = await notion.pages.update(
            page_id=page_id,
            properties={"Post Flair": {"select": {"name": new_flair}}}
        )
        return f"Флажок записи {page_id} изменён на {new_flair}" if response.get("object") == "page" else "Не удалось обновить флажок."
    except Exception as e:
        return f"Произошла ошибка при обновлении флажка: {e}"

# --- Существующие функции (для смены статуса и email) остаются без изменений ---

async def handle_change_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    notion_inst = context.bot_data["notion"]
    NOTION_TECHNICAL_ISSUES_DB = context.bot_data["NOTION_TECHNICAL_ISSUES_DB"]

    posts = await fetch_recent_posts(query, notion_inst, NOTION_TECHNICAL_ISSUES_DB)
    if not posts:
        await update.message.reply_text("Записи не найдены.")
        return
    keyboard = [
        [InlineKeyboardButton(
            post["properties"].get("Title", {}).get("rich_text", [{}])[0]
                .get("text", {}).get("content", "(Без названия)"),
            callback_data=f"csp_{post['id']}"
        )]
        for post in posts
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите запись для изменения статуса:", reply_markup=reply_markup)

async def handle_change_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    notion_inst = context.bot_data["notion"]
    NOTION_TECHNICAL_ISSUES_DB = context.bot_data["NOTION_TECHNICAL_ISSUES_DB"]

    posts = await fetch_recent_posts(query, notion_inst, NOTION_TECHNICAL_ISSUES_DB)
    if not posts:
        await update.message.reply_text("Записи не найдены.")
        return
    keyboard = [
        [InlineKeyboardButton(
            post["properties"].get("Title", {}).get("rich_text", [{}])[0]
                .get("text", {}).get("content", "(Без названия)"),
            callback_data=f"cep_{post['id']}"
        )]
        for post in posts
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите запись для изменения email:", reply_markup=reply_markup)

# --- Обработчик callback-запросов ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    notion_inst = context.bot_data["notion"]

    if data.startswith("csp_"):
        page_id = data[len("csp_"):]
        keyboard = [
            [InlineKeyboardButton(status, callback_data=f"ss|{page_id}|{STATUS_CODES[status]}")]
            for status in STATUS_CODES
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите новый статус:", reply_markup=reply_markup)

    elif data.startswith("ss|"):
        parts = data.split("|", 2)
        if len(parts) != 3:
            await query.edit_message_text("Некорректные данные.")
            return
        page_id, code = parts[1], parts[2]
        new_status = CODES_STATUS.get(code)
        if not new_status:
            await query.edit_message_text("Неизвестный статус.")
            return
        response = await update_post_status(notion_inst, page_id, new_status)
        await query.edit_message_text(response)

    elif data.startswith("cep_"):
        page_id = data[len("cep_"):]
        context.user_data["pending_email_page"] = page_id
        await query.edit_message_text("Введите новый email для выбранной записи:")

    # Новые ветки для команды /changeflair:
    elif data.startswith("cfp_"):
        # Пользователь выбрал запись для изменения флажка.
        page_id = data[len("cfp_"):]
        flairs = ["Help", "Discussion", "Suggestion", "Misc", "Gameplay", "Feedback"]
        keyboard = [
            [InlineKeyboardButton(fl, callback_data=f"cf|{page_id}|{fl}")]
            for fl in flairs
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите новый флажок:", reply_markup=reply_markup)

    elif data.startswith("cf|"):
        parts = data.split("|", 2)
        if len(parts) != 3:
            await query.edit_message_text("Некорректные данные.")
            return
        page_id, new_flair = parts[1], parts[2]
        response = await update_post_flair(notion_inst, page_id, new_flair)
        await query.edit_message_text(response)

    else:
        # Если ни одно условие не сработало, можно просто логировать
        await query.edit_message_text("Неизвестная команда.")

# --- Команды для изменения email и логирования входящих сообщений (оставляем без изменений) ---

async def handle_new_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_email_page" in context.user_data:
        new_email = update.message.text.strip()
        page_id = context.user_data.pop("pending_email_page")
        notion_inst = context.bot_data["notion"]
        response = await update_post_email(notion_inst, page_id, new_email)
        await update.message.reply_text(response)

async def log_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Получено сообщение: {update.message.text}")

# --- Словари для статусов ---
STATUS_CODES = {
    "In queue": "IQ",
    "Asked for the email": "AFE",
    "Made recommendations": "MR",
    "Made a ticket": "MT",
    "Solved": "S",
}
CODES_STATUS = {v: k for k, v in STATUS_CODES.items()}

ADD_YC_CHANNEL, ADD_YC_LINK, ADD_YC_COMMENT, ADD_YC_PROFILE, ADD_YC_AUTHOR = range(5)

async def add_yc_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите название Youtube канала:")
    return ADD_YC_CHANNEL

async def add_yc_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["add_yc_channel"] = update.message.text.strip()
    await update.message.reply_text("Введите ссылку на видео:")
    return ADD_YC_LINK

async def add_yc_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["add_yc_link"] = update.message.text.strip()
    await update.message.reply_text("Введите текст комментария:")
    return ADD_YC_COMMENT

async def add_yc_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["add_yc_comment"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("New to cloud", callback_data="ayc_profile|New to cloud")],
        [InlineKeyboardButton("User in choice", callback_data="ayc_profile|User in choice")],
        [InlineKeyboardButton("Boosteroid User", callback_data="ayc_profile|Boosteroid User")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите профиль:", reply_markup=reply_markup)
    return ADD_YC_PROFILE

async def add_yc_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, profile = query.data.split("|", 1)
    context.user_data["add_yc_profile"] = profile
    keyboard = [
        [InlineKeyboardButton("Ivan", callback_data="ayc_author|Ivan")],
        [InlineKeyboardButton("Arthur", callback_data="ayc_author|Arthur")],
        [InlineKeyboardButton("Denys", callback_data="ayc_author|Denys")],
        [InlineKeyboardButton("Roman", callback_data="ayc_author|Roman")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите автора комментария:", reply_markup=reply_markup)
    return ADD_YC_AUTHOR

async def add_yc_author(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, author = query.data.split("|", 1)
    context.user_data["add_yc_author"] = author

    notion_inst = context.bot_data["notion"]
    NOTION_YOUTUBE_DB = os.getenv("NOTION_YOUTUBE_DB")
    if not NOTION_YOUTUBE_DB:
        await query.edit_message_text("Не настроена база данных для Youtube комментариев.")
        return ConversationHandler.END

    properties = {
        "Youtube Channel": {
            "rich_text": [{"text": {"content": context.user_data.get("add_yc_channel", "")}}]
        },
        "Link to the video": {
            "url": context.user_data.get("add_yc_link", "")
        },
        "Text of the comment": {
            "rich_text": [{"text": {"content": context.user_data.get("add_yc_comment", "")}}]
        },
        "Profile": {
            "select": {"name": context.user_data.get("add_yc_profile", "")}
        },
        "Author ( Community Manager )": {
            "select": {"name": context.user_data.get("add_yc_author", "")}
        },
        "Date": {
            "date": {
                "start": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        }
    }
    try:
        response = await notion_inst.pages.create(
            parent={"database_id": NOTION_YOUTUBE_DB},
            properties=properties
        )
        if response.get("object") == "page":
            await query.edit_message_text("Комментарий успешно добавлен в базу данных.")
        else:
            await query.edit_message_text("Не удалось добавить комментарий.")
    except Exception as e:
        await query.edit_message_text(f"Ошибка при добавлении комментария: {e}")
    return ConversationHandler.END

async def add_yc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# --- Команда для запуска бота команд ---
async def start_telegram_commands_bot(NOTION_TOKEN, TELEGRAM_BOT_TOKEN, NOTION_TECHNICAL_ISSUES_DB):
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    await app.bot.delete_webhook(drop_pending_updates=True)
    notion_inst = create_notion_client(NOTION_TOKEN)
    app.bot_data["notion"] = notion_inst
    app.bot_data["NOTION_TECHNICAL_ISSUES_DB"] = NOTION_TECHNICAL_ISSUES_DB

    app.add_handler(CommandHandler("changestatus", handle_change_status))
    app.add_handler(CommandHandler("changeemail", handle_change_email))
    app.add_handler(CommandHandler("changeflair", handle_change_flair))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_email_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_messages))

    print("Бот запущен и слушает команды...")
    await app.run_polling()
