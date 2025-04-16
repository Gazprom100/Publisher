import os
import json
import datetime
import pytz
import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler

# ------------------------- Настройка данных через переменные окружения -------------------------
# 1. Сервисный аккаунт в переменной
if os.getenv("SERVICE_ACCOUNT_FILE_CONTENT"):
    with open("service_account.json", "w") as f:
        f.write(os.getenv("SERVICE_ACCOUNT_FILE_CONTENT"))
    SERVICE_ACCOUNT_FILE = "service_account.json"
else:
    # fallback, если переменной нет — локальный путь
    SERVICE_ACCOUNT_FILE = "/path/to/local/service_account.json"

# 2. Сопоставление каналов и листов (JSON), если есть в переменной
channel_sheets_str = os.getenv("CHANNELS_SHEETS")
if channel_sheets_str:
    CHANNELS_SHEETS = json.loads(channel_sheets_str)
else:
    # fallback — задаём прямо в коде
    CHANNELS_SHEETS = {
        "@KConsult_ing": "K.Consulting",
        "@Vegzzzbaj": "Vegzzzbaj"
    }

# 3. Остальные переменные (токен, ID таблицы) тоже можно взять из окружения
# Если нет, можно оставить хардкод
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1FUoF6V9whpPMfEml__rpqmGKPs5ohhLUI1s7D1N0SG8")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8006930667:AAHHpNFS3ySj8hzteC-mmg0YBtHnSf8jREs")

# ------------------------- Доступ к Google Sheets -------------------------
SCOPES_READ = ['https://www.googleapis.com/auth/spreadsheets.readonly']
credentials_read = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES_READ)
service_read = build('sheets', 'v4', credentials=credentials_read)

SCOPES_EDIT = ['https://www.googleapis.com/auth/spreadsheets']
credentials_edit = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES_EDIT)
service_edit = build('sheets', 'v4', credentials=credentials_edit)

# ------------------------- Инициализация бота -------------------------
bot = Bot(token=TELEGRAM_TOKEN)

# ------------------------- Глобальный event loop -------------------------
global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)

def run_async(coro):
    """Запускает асинхронную корутину через глобальный event loop."""
    return global_loop.run_until_complete(coro)

# ------------------------- Пример функций -------------------------

def get_posts_from_sheet(sheet_name):
    """Считываем данные из Google Таблицы... (пример)."""
    range_name = f"'{sheet_name}'!A2:F"
    try:
        result = service_read.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
    except Exception as ex:
        print(f"Ошибка при получении данных из листа {sheet_name}: {ex}")
        return []
    
    values = result.get('values', [])
    # ... Преобразуем значения ...
    posts = []
    # ...
    return posts

def publish_posts_all_channels():
    """Публикуем посты... (пример)."""
    now = datetime.datetime.now()
    for channel_id, sheet_name in CHANNELS_SHEETS.items():
        print(f"Обработка листа '{sheet_name}' для канала '{channel_id}'...")
        # ...
        # run_async(bot.send_message(...)) или send_photo(...)

if __name__ == '__main__':
    scheduler = BackgroundScheduler(timezone=pytz.utc)
    scheduler.add_job(publish_posts_all_channels, 'interval', minutes=1)
    scheduler.start()
    
    print("Бот запущен и отслеживает публикации...")
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Бот остановлен.")
