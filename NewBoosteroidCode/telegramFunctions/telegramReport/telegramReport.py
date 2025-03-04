import asyncio
from datetime import datetime, timedelta
from notion_client import AsyncClient
from telegram import Bot, InputFile
import os

# Глобальные переменные, которые будут инициализированы из main.py
NOTION_TOKEN = None
NOTION_TECHNICAL_ISSUES_DB = None
NOTION_ANALYTICS_DB = None
TELEGRAM_BOT_TOKEN = None
TELEGRAM_CHAT_ID = None
notion = None
bot = None

def init_report_vars(notion_token, notion_technical_issues_db, notion_analytics_db, telegram_bot_token, telegram_chat_id):
    """
    Инициализирует переменные модуля. Вызывается из main.py с передачей значений (в верхнем регистре).
    """
    global NOTION_TOKEN, NOTION_TECHNICAL_ISSUES_DB, NOTION_ANALYTICS_DB, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, notion, bot
    NOTION_TOKEN = notion_token
    NOTION_TECHNICAL_ISSUES_DB = notion_technical_issues_db
    NOTION_ANALYTICS_DB = notion_analytics_db
    TELEGRAM_BOT_TOKEN = telegram_bot_token
    TELEGRAM_CHAT_ID = telegram_chat_id
    notion = AsyncClient(auth=NOTION_TOKEN)
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

# --- Функции получения данных из Notion ---

def extract_date(prop):
    if prop and prop.get("date"):
        return prop["date"].get("start", "")
    return ""

def extract_title(prop):
    if prop and prop.get("title") and len(prop["title"]) > 0:
        return prop["title"][0].get("text", {}).get("content", "")
    return ""

def extract_rich_text(prop):
    if prop and prop.get("rich_text") and len(prop["rich_text"]) > 0:
        return prop["rich_text"][0].get("text", {}).get("content", "")
    return ""

async def get_technical_issues_report(start_iso: str, end_iso: str):
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_TECHNICAL_ISSUES_DB, filter=filter_body
    )
    results = response.get("results", [])
    count_help = 0
    moderator_response_count = 0
    status_counts = {
        "In queue": 0,
        "Asked for the email": 0,
        "Made recommendations": 0,
        "Made a ticket": 0,
        "Solved": 0,
    }
    for page in results:
        props = page.get("properties", {})
        post_flair = props.get("Post Flair", {}).get("select", {})
        if post_flair.get("name") == "Help":
            count_help += 1
            response_rt = props.get("Response from moderator", {}).get("rich_text", [])
            if response_rt and any(item.get("plain_text", "").strip() for item in response_rt):
                moderator_response_count += 1
            status = props.get("Status", {}).get("status", {})
            st_name = status.get("name")
            if st_name in status_counts:
                status_counts[st_name] += 1
    total = len(results)
    other_count = total - count_help
    return {
        "count_help": count_help,
        "status_counts": status_counts,
        "moderator_response_count": moderator_response_count,
        "total": total,
        "other_count": other_count
    }

async def get_reddit_comments_report(start_iso: str, end_iso: str):
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_TECHNICAL_ISSUES_DB.replace("TechnicalIssues", "RedditComments"),
        filter=filter_body
    )
    results = response.get("results", [])
    return len(results)

async def get_positive_negative_report(start_iso: str, end_iso: str):
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_ANALYTICS_DB, filter=filter_body
    )
    results = response.get("results", [])
    count_plus = 0
    count_minus = 0
    for page in results:
        reaction = page.get("properties", {}).get("Reaction", {}).get("select", {})
        if reaction.get("name") == "👍":
            count_plus += 1
        elif reaction.get("name") == "👎":
            count_minus += 1
    return count_plus, count_minus

async def get_work_count(start_iso: str, end_iso: str) -> int:
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_TECHNICAL_ISSUES_DB, filter=filter_body
    )
    results = response.get("results", [])
    return len(results)

async def get_youtube_comments_report(start_iso: str, end_iso: str):
    NOTION_YOUTUBE_DB = os.getenv("NOTION_YOUTUBE_DB")
    if not NOTION_YOUTUBE_DB:
        return {"total": 0, "authors": {"Ivan": 0, "Arthur": 0, "Denys": 0, "Roman": 0}}
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_YOUTUBE_DB,
        filter=filter_body
    )
    results = response.get("results", [])
    total = len(results)
    authors = {"Ivan": 0, "Arthur": 0, "Denys": 0, "Roman": 0}
    for page in results:
        props = page.get("properties", {})
        author_sel = props.get("Author ( Community Manager )", {}).get("select", {})
        author_name = author_sel.get("name")
        if author_name in authors:
            authors[author_name] += 1
    return {"total": total, "authors": authors}

async def get_detailed_technical_issues(start_iso: str, end_iso: str) -> list:
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_TECHNICAL_ISSUES_DB,
        filter=filter_body
    )
    results = response.get("results", [])
    details = []
    for page in results:
        props = page.get("properties", {})
        details.append({
            "Date": extract_date(props.get("Date")),
            "Username": extract_title(props.get("Username")),
            "Title": extract_rich_text(props.get("Title")),
            "Platform": extract_rich_text(props.get("Platform")),
            "URL": props.get("URL", {}).get("url", ""),
            "Description": extract_rich_text(props.get("Description")),
            "Status": props.get("Status", {}).get("status", {}).get("name", ""),
            "Email": props.get("Email", {}).get("email", ""),
            "Responsible moderator": extract_rich_text(props.get("Responsible moderator")),
            "Response from moderator": extract_rich_text(props.get("Response from moderator"))
        })
    return details

async def get_detailed_youtube_comments(start_iso: str, end_iso: str) -> list:
    NOTION_YOUTUBE_DB = os.getenv("NOTION_YOUTUBE_DB")
    if not NOTION_YOUTUBE_DB:
        return []
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_YOUTUBE_DB,
        filter=filter_body
    )
    results = response.get("results", [])
    details = []
    for page in results:
        props = page.get("properties", {})
        details.append({
            "Date": extract_date(props.get("Date")),
            "Youtube Channel": extract_rich_text(props.get("Youtube Channel")),
            "Link to the video": props.get("Link to the video", {}).get("url", ""),
            "Text of the comment": extract_rich_text(props.get("Text of the comment")),
            "Profile": props.get("Profile", {}).get("select", {}).get("name", ""),
            "Author ( Community Manager )": props.get("Author ( Community Manager )", {}).get("select", {}).get("name", "")
        })
    return details

async def get_detailed_reddit_comments(start_iso: str, end_iso: str) -> list:
    # Получаем ID базы для Reddit-комментариев
    db_id = NOTION_TECHNICAL_ISSUES_DB.replace("TechnicalIssues", "RedditComments")
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=db_id,
        filter=filter_body
    )
    results = response.get("results", [])
    details = []
    for page in results:
        props = page.get("properties", {})
        details.append({
            "Date": extract_date(props.get("Date")),
            "Username": extract_title(props.get("Username")),
            "Comment Text": extract_rich_text(props.get("Comment Text")),
            "URL": props.get("URL", {}).get("url", "")
        })
    return details

async def get_detailed_analytics(start_iso: str, end_iso: str) -> list:
    filter_body = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_iso}},
            {"property": "Date", "date": {"on_or_before": end_iso}}
        ]
    }
    response = await notion.databases.query(
        database_id=NOTION_ANALYTICS_DB,
        filter=filter_body
    )
    results = response.get("results", [])
    details = []
    for page in results:
        props = page.get("properties", {})
        details.append({
            "Date": extract_date(props.get("Date")),
            "Title": extract_rich_text(props.get("Title")),
            "Reaction": props.get("Reaction", {}).get("select", {}).get("name", ""),
            "URL": props.get("URL", {}).get("url", "")
        })
    return details


# --- Формирование текста отчета ---

def format_report(report_type: str, start_dt: datetime, end_dt: datetime,
                  tech: dict, reddit_comments: int, youtube_data: dict, pos_neg: tuple,
                  shift_label: str = None, shift_work: int = None) -> str:
    period = f"{start_dt.strftime('%d.%m.%Y %H:%M')} – {end_dt.strftime('%d.%m.%Y %H:%M')}"
    lines = []
    lines.append(f"Отчет ({report_type.capitalize()}) за период: {period}\n")
    lines.append("Технические проблемы (Technical Issues):\n")
    if tech["total"] == 0:
        lines.append("  Нет данных.")
    else:
        lines.append(f'  Постов с флажком "Help" : {tech["count_help"]}')
        lines.append("")
        lines.append("  Постов по статусам (только для 'Help'):")
        for st, cnt in tech["status_counts"].items():
            lines.append(f"    {st}: {cnt}")
        lines.append("")
        lines.append(f"  Постов с ответом модераторов: {tech['moderator_response_count']}")
        lines.append(f"  Постов с другими флажками: {tech['other_count']}")
        lines.append(f"  Всего постов: {tech['total']}")
        if shift_label and shift_work is not None:
            lines.append("")
            lines.append(f"  Работа в {shift_label} смене: {shift_work}")
    lines.append("")
    lines.append(f"Комментарии в Reddit: {reddit_comments}")
    lines.append("")
    # Добавляем информацию по YouTube комментариям
    lines.append(f"Комментарии на Youtube: {youtube_data['total']}")
    if youtube_data['total'] > 0:
        authors_breakdown = ", ".join(f"{author}: {count}" for author, count in youtube_data["authors"].items())
        lines.append(f"  По авторам: {authors_breakdown}")
    lines.append("")
    plus, minus = pos_neg
    lines.append("Посты с реакциями (Positive/Negative Posts):")
    lines.append(f"  👍: {plus}")
    lines.append(f"  👎: {minus}")
    if tech["total"] == 0 and reddit_comments == 0 and youtube_data["total"] == 0 and plus == 0 and minus == 0:
        lines.append("\nНедостаточно данных для отчета.")
    return "\n".join(lines)

async def create_detailed_report_file(start_iso: str, end_iso: str) -> str:
    tech = await get_detailed_technical_issues(start_iso, end_iso)
    youtube = await get_detailed_youtube_comments(start_iso, end_iso)
    reddit = await get_detailed_reddit_comments(start_iso, end_iso)
    analytics = await get_detailed_analytics(start_iso, end_iso)

    # Имя файла с отметкой времени
    filename = f"detailed_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("ПОДРОБНЫЙ ОТЧЁТ\n")
        f.write(f"Период: {start_iso} - {end_iso}\n\n")

        f.write("=== Technical Issues ===\n")
        if tech:
            for item in tech:
                for key, value in item.items():
                    f.write(f"{key}: {value}\n")
                f.write("-" * 40 + "\n")
        else:
            f.write("Нет данных.\n")
        f.write("\n")

        f.write("=== YouTube Comments ===\n")
        if youtube:
            for item in youtube:
                for key, value in item.items():
                    f.write(f"{key}: {value}\n")
                f.write("-" * 40 + "\n")
        else:
            f.write("Нет данных.\n")
        f.write("\n")

        f.write("=== Reddit Comments ===\n")
        if reddit:
            for item in reddit:
                for key, value in item.items():
                    f.write(f"{key}: {value}\n")
                f.write("-" * 40 + "\n")
        else:
            f.write("Нет данных.\n")
        f.write("\n")

        f.write("=== Analytics ===\n")
        if analytics:
            for item in analytics:
                for key, value in item.items():
                    f.write(f"{key}: {value}\n")
                f.write("-" * 40 + "\n")
        else:
            f.write("Нет данных.\n")
    return filename


# --- Отправка отчета через Telegram ---

async def send_report(report_type: str):
    if report_type == "night":
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = today - timedelta(days=1) + timedelta(hours=17)
        end_dt = today + timedelta(hours=4)
        shift_label = "ночную"
        shift_work = await get_work_count(start_dt.isoformat() + "Z", end_dt.isoformat() + "Z")
    elif report_type == "day":
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = today + timedelta(hours=4)
        end_dt = today + timedelta(hours=17)
        shift_label = "дневную"
        shift_work = await get_work_count(start_dt.isoformat() + "Z", end_dt.isoformat() + "Z")
    elif report_type == "weekly":
        now = datetime.utcnow()
        start_dt = now - timedelta(days=7)
        end_dt = now
        shift_label = None
        shift_work = None
    elif report_type == "monthly":
        now = datetime.utcnow()
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = now
        shift_label = None
        shift_work = None
    else:
        now = datetime.utcnow()
        start_dt = now - timedelta(days=1)
        end_dt = now
        shift_label = None
        shift_work = None

    start_iso = start_dt.isoformat() + "Z"
    end_iso = end_dt.isoformat() + "Z"

    tech = await get_technical_issues_report(start_iso, end_iso)
    reddit_comments = await get_reddit_comments_report(start_iso, end_iso)
    youtube_data = await get_youtube_comments_report(start_iso, end_iso)
    pos_neg = await get_positive_negative_report(start_iso, end_iso)
    report_text = format_report(report_type, start_dt, end_dt, tech, reddit_comments, youtube_data, pos_neg, shift_label, shift_work)

    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=report_text)
        print(f"{report_type.capitalize()} report sent successfully.")

        # Генерация подробного отчета и отправка файла
        detailed_filename = await create_detailed_report_file(start_iso, end_iso)
        with open(detailed_filename, "rb") as report_file:
            await bot.send_document(chat_id=TELEGRAM_CHAT_ID, document=InputFile(report_file, filename=detailed_filename))
        print("Подробный отчет отправлен.")
    except Exception as e:
        print(f"Ошибка при отправке отчета: {e}")

# --- Функции планирования ---

def seconds_until(target: datetime) -> float:
    now = datetime.now()
    delta = target - now
    return max(delta.total_seconds(), 0)

async def schedule_report(report_type: str, target_hour: int, target_minute: int):
    while True:
        now = datetime.now()
        if report_type in ("night", "day"):
            # Ежедневно – следующий запуск сегодня/завтра в заданное время
            next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
        elif report_type == "weekly":
            # Предположим, недельный отчёт должен идти в понедельник в заданное время.
            # Если сегодня не понедельник, вычисляем следующий понедельник.
            days_ahead = (0 - now.weekday()) % 7  # 0 = понедельник
            if days_ahead == 0 and now.time() >= (datetime.min + timedelta(hours=target_hour, minutes=target_minute)).time():
                days_ahead = 7
            next_run = (now + timedelta(days=days_ahead)).replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        elif report_type == "monthly":
            # Ежемесячно – первый день следующего месяца в заданное время.
            if now.month == 12:
                next_run = now.replace(year=now.year+1, month=1, day=1, hour=target_hour, minute=target_minute, second=0, microsecond=0)
            else:
                next_run = now.replace(month=now.month+1, day=1, hour=target_hour, minute=target_minute, second=0, microsecond=0)
        wait_sec = seconds_until(next_run)
        print(f"Next {report_type} report scheduled in {wait_sec:.0f} seconds at {next_run}")
        await asyncio.sleep(wait_sec)
        await send_report(report_type)

# --- Экспортируемая функция для запуска отчетов ---
async def run_reports():
    print("Отправляю тестовый отчет...")
    await send_report("night")
    await send_report("day")
    night_task = asyncio.create_task(schedule_report("night", 4, 0))
    day_task = asyncio.create_task(schedule_report("day", 17, 0))
    weekly_task = asyncio.create_task(schedule_report("weekly", 17, 0))
    monthly_task = asyncio.create_task(schedule_report("monthly", 17, 0))
    await asyncio.gather(night_task, day_task, weekly_task, monthly_task)

if __name__ == "__main__":
    asyncio.run(run_reports())
