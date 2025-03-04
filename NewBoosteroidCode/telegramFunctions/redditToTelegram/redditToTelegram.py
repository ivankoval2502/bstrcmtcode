import aiohttp
import asyncpraw
import asyncio
import ssl
import certifi
import os
from telegram import Bot, Update
from telegram.ext import MessageHandler, filters
import re
from dotenv import load_dotenv
from datetime import datetime
import nest_asyncio

load_dotenv(dotenv_path="../../.env")

async def send_notification(bot: Bot, message: str):
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Ошибка при отправке уведомления в Telegram: {e}")

async def track_posts(subreddit, bot: Bot, IGNORED_USERS):
    async for post in subreddit.stream.submissions(skip_existing=True):
        author = post.author
        if author and author.name in IGNORED_USERS:
            print(f"Пост от {author.name} игнорируется.")
            continue
        print("Новый пост:", post.title)
        await send_notification(
            bot=bot,
            message=f"📌 Новый пост: {post.title}\n🔗 Ссылка: {post.url}"
        )

async def track_comments(subreddit, bot: Bot, IGNORED_USERS):
    async for comment in subreddit.stream.comments(skip_existing=True):
        author = comment.author
        if author and author.name in IGNORED_USERS:
            print(f"Комментарий от {author.name} игнорируется.")
            continue
        print("Новый комментарий:", comment.body)
        await send_notification(
            bot=bot,
            message=f"💬 Новый комментарий:\n\n{comment.body}\n🔗 Ссылка: https://www.reddit.com{comment.permalink}",
        )

async def start_tracking(bot: Bot, subreddit_name, IGNORED_USERS):
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        reddit = asyncpraw.Reddit(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            user_agent=os.getenv("USER_AGENT"),
            requestor_kwargs={"session": session},
        )
        subreddit = await reddit.subreddit(subreddit_name)
        print(f"Успешно подключено к сабреддиту: {subreddit_name}")
        post_task = asyncio.create_task(track_posts(subreddit, bot, IGNORED_USERS))
        comment_task = asyncio.create_task(track_comments(subreddit, bot, IGNORED_USERS))
        await asyncio.gather(post_task, comment_task)

async def get_reddit_data(reddit_url):
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        reddit = asyncpraw.Reddit(
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET"),
            user_agent=os.getenv("USER_AGENT"),
            requestor_kwargs={"session": session},
        )
        try:
            url_parts = reddit_url.rstrip("/").split("/")
            if "comments" in url_parts and len(url_parts) > 7:
                submission_id = url_parts[url_parts.index("comments") + 1]
                comment_id = url_parts[-1]
                if comment_id.isalnum():
                    print(f"Extracted submission ID: {submission_id}")
                    print(f"Extracted comment ID: {comment_id}")
                    comment = await reddit.comment(comment_id)
                    await comment.load()
                    print(f"Комментарий: {comment.body}")
                    return f"Комментарий: {comment.body}", comment.body, reddit_url
            if "comments" in url_parts and len(url_parts) > 6:
                submission_id = url_parts[url_parts.index("comments") + 1]
                print(f"Extracted submission ID: {submission_id}")
                submission = await reddit.submission(submission_id)
                await submission.load()
                print(f"Пост: {submission.title} | {submission.selftext}")
                return submission.title, submission.selftext or "[Без текста]", reddit_url
            print("Invalid Reddit URL format")
            return None, None, None
        except Exception as e:
            print(f"Ошибка при получении данных с Reddit: {e}")
            return None, None, None

async def add_reaction_to_notion(post_title, post_content, post_url, reaction_type):
    current_date = datetime.utcnow().isoformat()
    if len(post_content) > 2000:
        post_content = post_content[:1997] + "..."
    headers = {
        "Authorization": f"Bearer {os.getenv('NOTION_TOKEN')}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": os.getenv("NOTION_ANALYTICS_DB")},
        "properties": {
            "Title": {"title": [{"text": {"content": post_title}}]},
            "Content": {"rich_text": [{"text": {"content": post_content}}]},
            "URL": {"url": post_url},
            "Reaction": {"select": {"name": reaction_type}},
            "Date": {"date": {"start": current_date}},
        }
    }
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.post('https://api.notion.com/v1/pages', headers=headers, json=data) as response:
            if response.status == 200:
                print(f"Reaction '{reaction_type}' added successfully!")
            else:
                print(f"Failed to add reaction to Notion: {response.status} - {await response.text()}")

async def handle_message(update: Update, context):
    message = update.message.text
    user_id = update.message.from_user.id
    print(f"Recieved message: {message}")
    reddit_url = None
    if update.message.reply_to_message:
        reply_message = update.message.reply_to_message.text
        match = re.search(r'https?://www\.reddit\.com/r/BoosteroidCommunity/comments/\S+', reply_message)
        if match:
            reddit_url = match.group(0)
            print(f"Found Reddit URL: {reddit_url}")
            post_title, post_content, post_url = await get_reddit_data(reddit_url)
            if post_title:
                if "👍" in message:
                    reaction_type = "👍"
                    print(f"Received positive feedback from {user_id}")
                    await add_reaction_to_notion(post_title, post_content, post_url, reaction_type)
                elif "👎" in message:
                    reaction_type = "👎"
                    print(f"Received negative feedback from {user_id}")
                    await add_reaction_to_notion(post_title, post_content, post_url, reaction_type)
                else:
                    print(f"Recieved message: {message}")
            else:
                print(f"Failed to get data for Reddit URL: {reddit_url}")
        else:
            print("No valid Reddit URL found in the reply message.")
    else:
        print("This is not a reply message.")

nest_asyncio.apply()
