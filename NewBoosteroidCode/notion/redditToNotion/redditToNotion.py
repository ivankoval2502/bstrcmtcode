import os
import uuid
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import time
import asyncpraw
import aiohttp
import ssl
import certifi
import asyncio
import notion_client
import re

load_dotenv()  # Файл .env должен быть в корне проекта

print("NOTION_TECHNICAL_ISSUES_DB =", os.getenv("NOTION_TECHNICAL_ISSUES_DB"))

# Инициализируем клиент Notion (синхронно)
notion = notion_client.Client(auth=os.getenv("NOTION_TOKEN"))

REDDIT_CLIENT_ID = os.getenv("CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("USER_AGENT")
NOTION_TECHNICAL_ISSUES_DB = os.getenv("NOTION_TECHNICAL_ISSUES_DB")

MODERATORS = {"Alex_Boosteroid", "Andrew__Boosteroid", "Arthur_Boosteroid", "Mark_Boosteroid"}
VALID_FLAIRS = {"help", "discussion", "suggestion", "misc", "gameplay", "feedback"}

def remove_emojis(text):
    return re.sub(r':\w+:', '', text)

def clean_flair(flair):
    flair_mapping = {
        'help': 'Help',
        'discussion': 'Discussion',
        'suggestion': 'Suggestion',
        'misc': 'Misc',
        'gameplay': 'Gameplay',
        'feedback': 'Feedback'
    }
    cleaned_flair = remove_emojis(flair.strip().lower())
    return flair_mapping.get(cleaned_flair, "No Flair")

def add_post_to_notion(post, notion, NOTION_TECHNICAL_ISSUES_DB):
    database_id = NOTION_TECHNICAL_ISSUES_DB
    if not database_id:
        raise ValueError("DATABASE NOT FOUND")
    post_timestamp = datetime.fromtimestamp(post.created_utc, timezone.utc).isoformat()
    flair_text = clean_flair(post.link_flair_text) if post.link_flair_text else "No Flair"
    new_page = {
        "parent": {"database_id": database_id},
        "properties": {
            "Date": {"date": {"start": post_timestamp}},
            "ID": {"rich_text": [{"text": {"content": post.id}}]},
            "Username": {"title": [{"text": {"content": post.author.name}}]},
            "Title": {"rich_text": [{"text": {"content": post.title}}]},
            "Platform": {"select": {"name": "Reddit"}},
            "URL": {"url": post.url},
            "Description": {"rich_text": [{"text": {"content": post.selftext}}]},
            "Status": {"status": {"name": "In queue"}},
            "Post Flair": {"select": {"name": flair_text}},
            "Responsible moderator": {"rich_text": []},
            "Response from moderator": {"rich_text": []},
        }
    }
    notion.pages.create(**new_page)

def update_notion_with_moderator_comment(notion, NOTION_TECHNICAL_ISSUES_DB, post_id, mod_name, comment):
    query = notion.databases.query(
        database_id=NOTION_TECHNICAL_ISSUES_DB,
        filter={"property": "ID", "rich_text": {"equals": post_id}}
    )
    if query["results"]:
        page_id = query["results"][0]["id"]
        notion.pages.update(page_id, properties={
            "Responsible moderator": {"rich_text": [{"text": {"content": mod_name}}]},
            "Response from moderator": {"rich_text": [{"text": {"content": comment}}]},
        })

async def scan_posts_and_add_to_notion(notion, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, NOTION_TECHNICAL_ISSUES_DB):
    print(f"Запуск scan_posts_and_add_to_notion с {REDDIT_CLIENT_ID}")
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            requestor_kwargs={"session": session}
        )
        subreddit = await reddit.subreddit("BoosteroidCommunity")
        print(f"Поиск постов с флаерами: {VALID_FLAIRS} за последние 60 минут")
        try:
            one_hour_ago = int(time.time()) - 3600  # актуальное время для каждого вызова
            async for post in subreddit.new(limit=100):
                try:
                    if post.created_utc >= one_hour_ago:
                        print(f"Пост найден: {post.title}")
                        flair_text = remove_emojis(post.link_flair_text.strip().lower()) if post.link_flair_text else ""
                        if flair_text in {remove_emojis(f.lower()) for f in VALID_FLAIRS}:
                            print(f"Добавляю пост: {post.title} с флаером '{flair_text}'")
                            add_post_to_notion(post, notion, NOTION_TECHNICAL_ISSUES_DB)
                            await check_moderator_comments(post, notion, NOTION_TECHNICAL_ISSUES_DB)
                        else:
                            print(f"Пост не соответствует флаеру: {post.title}")
                except Exception as e:
                    print(f"Ошибка при обработке поста {post.id}: {e}")
        except Exception as e:
            print(f"Ошибка при получении постов: {e}")
            await asyncio.sleep(30)

async def periodic_scan_posts():
    while True:
        try:
            await scan_posts_and_add_to_notion(notion, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, NOTION_TECHNICAL_ISSUES_DB)
        except Exception as e:
            print(f"Ошибка в periodic_scan_posts: {e}")
        await asyncio.sleep(3600)


async def check_moderator_comments(post, notion, NOTION_TECHNICAL_ISSUES_DB):
    await post.load()
    await post.comments.replace_more(limit=0)
    async for comment in post.comments:
        if comment.author and comment.author.name in MODERATORS:
            print(f"Модератор {comment.author.name} оставил комментарий: {comment.body}")
            update_notion_with_moderator_comment(notion, NOTION_TECHNICAL_ISSUES_DB, post.id, comment.author.name, comment.body)

async def scan_moderator_comments(notion, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, NOTION_TECHNICAL_ISSUES_DB):
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            requestor_kwargs={"session": session}
        )
        subreddit = await reddit.subreddit("BoosteroidCommunity")
        print("Начинаю стрим комментариев для модераторов...")
        async for comment in subreddit.stream.comments(skip_existing=True):
            if comment.author and comment.author.name in MODERATORS:
                print(f"Новый комментарий модератора {comment.author.name}: {comment.body}")
                post_id = comment.link_id.split('_')[-1]
                update_notion_with_moderator_comment(notion, NOTION_TECHNICAL_ISSUES_DB, post_id, comment.author.name, comment.body)

async def update_old_posts_to_solved(notion, NOTION_TECHNICAL_ISSUES_DB):
    one_week_ago_iso = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    filter_body = {
        "and": [
            {"property": "Date", "date": {"before": one_week_ago_iso}},
            {"property": "Status", "status": {"does_not_equal": "Solved"}}
        ]
    }
    query = notion.databases.query(database_id=NOTION_TECHNICAL_ISSUES_DB, filter=filter_body)
    results = query.get("results", [])
    print(f"Найдено постов старше недели для обновления: {len(results)}")
    for page in results:
        page_id = page["id"]
        print(f"Обновление статуса поста {page_id} на Solved")
        notion.pages.update(page_id, properties={
            "Status": {"status": {"name": "Solved"}}
        })

async def periodic_update_old_posts():
    while True:
        await update_old_posts_to_solved(notion, NOTION_TECHNICAL_ISSUES_DB)
        await asyncio.sleep(1800)

async def run_reddit_to_notion():
    task1 = asyncio.create_task(periodic_scan_posts())
    task2 = asyncio.create_task(scan_moderator_comments(notion, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, NOTION_TECHNICAL_ISSUES_DB))
    task3 = asyncio.create_task(periodic_update_old_posts())
    await asyncio.gather(task1, task2, task3)

