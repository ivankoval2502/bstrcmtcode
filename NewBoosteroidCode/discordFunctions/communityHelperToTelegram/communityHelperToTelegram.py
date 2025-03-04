import discord
import uuid  # Добавляем для генерации уникального ID
from telegram import Bot
from discord.ext import commands
import os
import ssl
import certifi
import aiohttp
import asyncio
from dotenv import load_dotenv
from notion_client import Client
from datetime import datetime

load_dotenv(dotenv_path="../../.env")

MODERATOR_TAGS = ["[Mod] Alex", "[Mod] Artorias", "[Mod] Denys", "[Mod] Andrii", "artorias_the_one", "ggdeviant.",
                  "bomboclat0109", "andrii4496"]

class DiscordBot:
    def __init__(self, TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, NOTION_TECHNICAL_ISSUES_DB, NOTION_TOKEN):
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        self.bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())
        self.tg_bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.NOTION_TECHNICAL_ISSUES_DB = NOTION_TECHNICAL_ISSUES_DB
        self.NOTION_TOKEN = NOTION_TOKEN

        @self.bot.command(description="Sends your report to the support team.")
        async def communityhelper(ctx, *, text: str):
            request_id = str(uuid.uuid4())  # Генерируем уникальный ID
            chat_name = ctx.channel.name if ctx.guild else f"Личные сообщения с {ctx.author.name}"
            message = f"📢 {ctx.author.name} ({chat_name}) отправил сообщение:\n{text}\n\n🆔 Request ID: {request_id}"

            # Отправка в Telegram
            await self.tg_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

            # **Отправка в Notion**
            await self.send_to_notion(ctx.author.name, text, request_id)

            # Подтверждение в Discord (вместо create_task)
            await self.send_report(ctx, text, request_id)  # Прямо вызываем функцию

        @self.bot.event
        async def on_message(message):
            if message.author == self.bot.user:
                return

            chat_name = message.channel.name if message.guild else f"ЛС с {message.author.name}"

            mentioned_mods = [
                user for user in message.mentions
                if user.name in MODERATOR_TAGS or user.display_name in MODERATOR_TAGS
            ]

            if mentioned_mods:
                mods_names = ", ".join([mod.display_name for mod in mentioned_mods])
                alert_msg = f"⚠️ {message.author.name} упомянул {mods_names} в {chat_name}:\n{message.content}"

                await self.tg_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=alert_msg)

            await self.bot.process_commands(message)

    async def send_report(self, ctx, message_text, request_id):
        try:
            # Отправляем в Discord подтверждение с сообщением пользователя
            confirmation_message = (
                f"Your report has been sent to support!\n"
                f"🆔 Request ID: {request_id}\n"
                f"Your message text: {message_text}\n"
                "Please wait for a response from the moderator and save the report ID"
            )
            await ctx.author.send(confirmation_message)  # Отправляем в личку
        except Exception as e:
            print(f"Ошибка при отправке личного сообщения: {e}")

    async def send_to_notion(self, username, description, request_id):

        notion = Client(auth=self.NOTION_TOKEN)

        try:
            notion.pages.create(
                parent={"database_id": self.NOTION_TECHNICAL_ISSUES_DB},
                properties={
                    "ID": {"rich_text": [{"text": {"content": str(request_id)}}]},
                    "Date": {"date": {"start": datetime.utcnow().isoformat()}},
                    "Title": {"rich_text": [{"text": {"content": description}}]},
                    "Username": {"title": [{"text": {"content": username}}]},
                    "Platform": {"select": {"name": "Discord"}},
                    "Post Flair": {"select": {"name": "Help"}},
                    "Description": {"rich_text": [{"text": {"content": description}}]},
                    "Status": {"status": {"name": "In queue"}},
                }
            )
            print(f"✅ Данные отправлены в Notion: {username} - {description} (ID: {request_id})")
        except Exception as e:
            print(f"❌ Ошибка при отправке в Notion: {e}")
            # Логируем ошибки, если что-то пошло не так
            raise e  # Вызываем ошибку, чтобы она была видна в консоли или журнале

    async def run(self, DISCORD_TOKEN):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self.ssl_context)) as session:
            self.bot.session = session
            await self.bot.start(DISCORD_TOKEN)

def start_discord_bot(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, DISCORD_TOKEN, NOTION_TECHNICAL_ISSUES_DB, NOTION_TOKEN):
    bot_instance = DiscordBot(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, NOTION_TECHNICAL_ISSUES_DB, NOTION_TOKEN)

    async def run_bot():
        await bot_instance.run(DISCORD_TOKEN)

    asyncio.run(run_bot())  # Запускаем бота
