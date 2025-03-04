import asyncio
import os
from dotenv import load_dotenv
import asyncpraw
from notion.redditToNotion.redditToNotion import run_reddit_to_notion
from notion.redditCommentsToNotion.redditCommentsToNotion import scan_comments_and_add_to_notion
from telegramFunctions.redditToTelegram.redditToTelegram import start_tracking, handle_message
from telegramFunctions.telegramReport.telegramReport import init_report_vars, run_reports
from telegramFunctions.сhangeStatus.changeStatus import (
    handle_change_status,
    handle_change_email,
    handle_change_flair,
    button_handler,
    create_notion_client,
    handle_new_email_input,
    add_yc_start, add_yc_channel, add_yc_link, add_yc_comment,
    add_yc_profile, add_yc_author, add_yc_cancel,
    ADD_YC_CHANNEL, ADD_YC_LINK, ADD_YC_COMMENT, ADD_YC_PROFILE, ADD_YC_AUTHOR
)
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from notion_client import Client
import threading
import sys
import logging

load_dotenv()

print("NOTION_TECHNICAL_ISSUES_DB =", os.getenv("NOTION_TECHNICAL_ISSUES_DB"))

# Инициализация переменных
REDDIT_CLIENT_ID = os.getenv("CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("USER_AGENT")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NOTION_TECHNICAL_ISSUES_DB = os.getenv("NOTION_TECHNICAL_ISSUES_DB")
IGNORED_USERS = os.getenv("IGNORED_USERS", "").split(",")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NOTION_ANALYTICS_DB = os.getenv("NOTION_ANALYTICS_DB")

# Инициализация переменных для отчётов
init_report_vars(NOTION_TOKEN, NOTION_TECHNICAL_ISSUES_DB, NOTION_ANALYTICS_DB, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

notion = Client(auth=NOTION_TOKEN)
reddit = asyncpraw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

# Функция для запуска Discord-бота
def run_discord_bot():
    from discordFunctions.communityHelperToTelegram.communityHelperToTelegram import start_discord_bot
    start_discord_bot(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, DISCORD_TOKEN, NOTION_TECHNICAL_ISSUES_DB, NOTION_TOKEN)

async def unified_message_handler(update, context):
    if "pending_email_page" in context.user_data:
        await handle_new_email_input(update, context)
    else:
        await handle_message(update, context)

async def start_unified_telegram_bot(app: Application):
    print("Объединённый Telegram бот запущен.")
    await app.run_polling()

async def periodic_task(interval, task, *args):
    while True:
        try:
            print(f"Запуск задачи {task.__name__}...")
            await task(*args)
            print(f"Задача {task.__name__} выполнена. Ожидание {interval} секунд...")
        except Exception as e:
            print(f"Ошибка в задаче {task.__name__}: {e}")
        await asyncio.sleep(interval)

log_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "app.log")),
        logging.StreamHandler()
    ]
)

class LoggerWriter:
    def __init__(self, level):
        self.level = level
        self._buffer = ""
    def write(self, message):
        if message.strip():
            self._buffer += message
            if "\n" in self._buffer:
                for line in self._buffer.splitlines():
                    self.level(line)
                self._buffer = ""
    def flush(self):
        if self._buffer:
            self.level(self._buffer)
            self._buffer = ""
sys.stdout = LoggerWriter(logging.info)
sys.stderr = LoggerWriter(logging.error)

async def main():
    print("Запуск задач...")

    # Запуск Discord-бота
    discord_thread = threading.Thread(target=run_discord_bot)
    discord_thread.start()

    # Создаём единый экземпляр Telegram-бота
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.bot_data["notion"] = create_notion_client(NOTION_TOKEN)
    app.bot_data["NOTION_TECHNICAL_ISSUES_DB"] = NOTION_TECHNICAL_ISSUES_DB

    app.add_handler(CommandHandler("changestatus", handle_change_status))
    app.add_handler(CommandHandler("changeemail", handle_change_email))
    app.add_handler(CommandHandler("changeflair", handle_change_flair))
    add_yc_conv = ConversationHandler(
        entry_points=[CommandHandler("addyc", add_yc_start)],
        states={
            ADD_YC_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_yc_channel)],
            ADD_YC_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_yc_link)],
            ADD_YC_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_yc_comment)],
            ADD_YC_PROFILE: [CallbackQueryHandler(add_yc_profile, pattern="^ayc_profile\\|")],
            ADD_YC_AUTHOR: [CallbackQueryHandler(add_yc_author, pattern="^ayc_author\\|")]
        },
        fallbacks=[CommandHandler("cancel", add_yc_cancel)]
    )
    app.add_handler(add_yc_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_message_handler))

    telegram_task = asyncio.create_task(start_unified_telegram_bot(app))

    # Передаём единый экземпляр бота для отслеживания Reddit
    bot = app.bot
    tracking_task = asyncio.create_task(start_tracking(bot, SUBREDDIT_NAME, IGNORED_USERS))

    reddit_notion_task = asyncio.create_task(run_reddit_to_notion())

    comments_task = asyncio.create_task(
        periodic_task(3600, scan_comments_and_add_to_notion, reddit, notion, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, IGNORED_USERS)
    )

    report_task = asyncio.create_task(run_reports())

    await asyncio.gather(telegram_task, tracking_task, reddit_notion_task, comments_task, report_task)

asyncio.run(main())
