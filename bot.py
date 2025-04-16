import datetime
import pytz
import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler

# ------------------------- Конфигурация -------------------------
SERVICE_ACCOUNT_FILE = '/Users/evgenikrasnov/Downloads/peppy-primacy-457011-i0-b081e206fb2b.json'
SPREADSHEET_ID = '1FUoF6V9whpPMfEml__rpqmGKPs5ohhLUI1s7D1N0SG8'
TELEGRAM_TOKEN = '8006930667:AAHHpNFS3ySj8hzteC-mmg0YBtHnSf8jREs'

# Сопоставление каналов и листов
CHANNELS_SHEETS = {
    "@KConsult_ing": "К.Consulting",
    "@Vegzzzbaj": "Vegzzzbaj"  # Обновите имя листа в соответствии с вашей таблицей
}

# ------------------------- Доступ к Google Sheets -------------------------
SCOPES_READ = ['https://www.googleapis.com/auth/spreadsheets.readonly']
credentials_read = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES_READ)
service_read = build('sheets', 'v4', credentials=credentials_read)

SCOPES_EDIT = ['https://www.googleapis.com/auth/spreadsheets']
credentials_edit = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES_EDIT)
service_edit = build('sheets', 'v4', credentials=credentials_edit)

# ------------------------- Инициализация Telegram-бота -------------------------
bot = Bot(token=TELEGRAM_TOKEN)

# ------------------------- Устанавливаем глобальный event loop -------------------------
global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)

def run_async(coro):
    """Запускает асинхронную корутину через глобальный event loop."""
    return global_loop.run_until_complete(coro)

# ------------------------- Функция для формирования диапазона -------------------------
def get_range_name(sheet_name):
    """
    Формирует диапазон для чтения данных из листа.
    Если имя листа состоит только из букв и цифр, оно возвращается без кавычек,
    иначе имя оборачивается в одинарные кавычки.
    """
    if sheet_name.isalnum():
        return f"{sheet_name}!A2:F"
    else:
        return f"'{sheet_name}'!A2:F"

# ------------------------- Функция для получения постов -------------------------
def get_posts_from_sheet(sheet_name):
    """
    Читает данные с листа Google Таблицы.
    Ожидаемый диапазон: A2:F, где:
      - A: Дата (dd.mm.yyyy)
      - B: Время (HH:MM)
      - C: Фото (URL или пусто)
      - D: Пост (текст)
      - E: Подтверждение (TRUE, 1, ДА)
      - F: Состояние (ожидает, выложен и т.д.)
    """
    range_name = get_range_name(sheet_name)
    try:
        result = service_read.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
    except Exception as ex:
        print(f"Ошибка при получении данных из листа {sheet_name}: {ex}")
        return []
    
    values = result.get('values', [])
    posts = []
    for row in values:
        if len(row) < 6:
            continue

        date_str = row[0].strip()    # Например, "25.04.2025"
        time_str = row[1].strip()    # Например, "15:30"
        datetime_str = f"{date_str} {time_str}"
        try:
            post_time = datetime.datetime.strptime(datetime_str, '%d.%m.%Y %H:%M')
        except ValueError:
            print(f"Неверный формат даты/времени в листе {sheet_name}: {datetime_str}")
            continue

        photo = row[2].strip()
        text = row[3].strip()
        editor_confirm = row[4].strip().lower() in ["true", "1", "да"]
        state = row[5].strip().lower()
        
        post = {
            'time': post_time,
            'photo': photo,
            'text': text,
            'editor_confirm': editor_confirm,
            'state': state,
        }
        print(f"Получена запись из листа {sheet_name}: {post}")
        posts.append(post)
    return posts

# ------------------------- Функция для обновления статуса -------------------------
def update_post_status(sheet_name, row_index, new_status="выложен"):
    """
    Обновляет статус записи в указанном листе (столбец F).
    row_index — индекс записи (начинается с 0; прибавляем 2, если первая строка – заголовки)
    """
    row_number = row_index + 2
    if sheet_name.isalnum():
        range_to_update = f"{sheet_name}!F{row_number}"
    else:
        range_to_update = f"'{sheet_name}'!F{row_number}"
    value_input_option = "RAW"
    values = [[new_status]]
    body = {'values': values}
    
    try:
        result = service_edit.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_to_update,
            valueInputOption=value_input_option,
            body=body
        ).execute()
        print(f"Лист [{sheet_name}], строка {row_number} обновлена: {result.get('updatedCells')} ячеек изменено.")
    except Exception as e:
        print(f"Ошибка при обновлении статуса в листе {sheet_name}: {e}")

# ------------------------- Функция публикации -------------------------
def publish_posts_all_channels():
    """
    Для каждого канала:
      - Извлекает посты из соответствующего листа.
      - Если запись удовлетворяет условиям (подтверждена, время наступило, статус "ожидает"),
        отправляет сообщение в Telegram и обновляет статус на "выложен".
    """
    now = datetime.datetime.now()
    print(f"Текущее время: {now}")
    for channel_id, sheet_name in CHANNELS_SHEETS.items():
        print(f"Обработка листа '{sheet_name}' для канала '{channel_id}'...")
        posts = get_posts_from_sheet(sheet_name)
        for idx, post in enumerate(posts):
            print(f"Проверяем запись: {post}")
            if post['editor_confirm'] and post['time'] <= now and post['state'] == 'ожидает':
                try:
                    if post['photo']:
                        run_async(bot.send_photo(chat_id=channel_id,
                                                   photo=post['photo'],
                                                   caption=post['text']))
                    else:
                        run_async(bot.send_message(chat_id=channel_id,
                                                   text=post['text']))
                    print(f"[{datetime.datetime.now()}] Опубликовано в {channel_id}: {post['text']}")
                    update_post_status(sheet_name, idx, new_status="выложен")
                except Exception as e:
                    print(f"Ошибка при публикации для канала {channel_id}: {e}")

# ------------------------- Основной блок -------------------------
if __name__ == '__main__':
    scheduler = BackgroundScheduler(timezone=pytz.utc)
    scheduler.add_job(publish_posts_all_channels, 'interval', minutes=1)
    scheduler.start()
    
    print("Бот запущен и отслеживает публикации для всех каналов...")
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Бот остановлен.")
