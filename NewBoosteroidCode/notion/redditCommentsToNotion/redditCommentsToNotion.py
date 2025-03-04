import os
from dotenv import load_dotenv
from datetime import datetime
import time
import asyncpraw
import aiohttp
import ssl
import certifi

load_dotenv(dotenv_path="../../.env")

##one_hour_ago = int(time.time()) - 3600

def add_comments_to_notion(comment, notion):
    database_id = os.getenv("NOTION_REDDIT_COMMENTS_DB")

    if not database_id:
        raise ValueError("COMMENTS DATABASE NOT FOUND")

    comment_timestamp = datetime.utcfromtimestamp(comment.created_utc).isoformat()

    new_page = {
        "parent": {"database_id": database_id},
        "properties": {
            "Date": {
                "date": {
                    "start": comment_timestamp
                }
            },
            "Username": {
                "title": [{"text": {"content": comment.author.name}}]
            },
            "Comment Text": {
                "rich_text": [{"text": {"content": comment.body}}]
            },
            "URL": {
                "url": f"https://reddit.com{comment.permalink}"
            }
        }
    }

    notion.pages.create(**new_page)

async def scan_comments_and_add_to_notion(reddit, notion, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, IGNORED_USERS):
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            requestor_kwargs={"session": session}
        )

        subreddit = await reddit.subreddit("BoosteroidCommunity")
        # Каждый раз вычисляем порог времени
        one_hour_ago = int(time.time()) - 3600

        async for comment in subreddit.comments(limit=100):
            if comment.author and comment.author.name in IGNORED_USERS:
                print(f"Комментарий от {comment.author} игнорируется")
                continue

            if comment.created_utc >= one_hour_ago:
                print(f"Найден новый комментарий в сабреддите: {comment.body}")
                add_comments_to_notion(comment, notion)
            else:
                break
