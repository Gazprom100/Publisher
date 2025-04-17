from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO
import json
import os
from datetime import datetime
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import threading
import asyncio
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler
import eventlet
eventlet.monkey_patch()

# Определяем базовый путь для шаблонов и статических файлов
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Создаем директории, если они не существуют
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = Flask(__name__, 
            template_folder=TEMPLATE_DIR,
            static_folder=STATIC_DIR)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

# Загрузка конфигурации из переменных окружения
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1FUoF6V9whpPMfEml__rpqmGKPs5ohhLUI1s7D1N0SG8")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8006930667:AAHHpNFS3ySj8hzteC-mmg0YBtHnSf8jREs")

# Конфигурация каналов
CHANNELS_SHEETS = {
    "@KConsult_ing": "K.Consulting",
    "@Vegzzzbaj": "Vegzzzbaj"
}

# Инициализация сервиса Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

# Инициализация Telegram бота
bot = Bot(token=TELEGRAM_TOKEN)

# Глобальный event loop для асинхронных операций
global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)

def run_async(coro):
    return global_loop.run_until_complete(coro)

def get_range_name(sheet_name):
    return f"'{sheet_name}'!A2:F"

def get_posts_from_sheet(sheet_name):
    range_name = get_range_name(sheet_name)
    try:
        result = service.spreadsheets().values().get(
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
        date_str = row[0].strip()
        time_str = row[1].strip()
        datetime_str = f"{date_str} {time_str}"
        try:
            post_time = datetime.strptime(datetime_str, '%d.%m.%Y %H:%M')
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

def update_post_status(sheet_name, row_index, new_status="выложен"):
    row_number = row_index + 2
    range_to_update = f"'{sheet_name}'!F{row_number}"
    value_input_option = "RAW"
    values = [[new_status]]
    body = {'values': values}
    try:
        result = service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_to_update,
            valueInputOption=value_input_option,
            body=body
        ).execute()
        print(f"Лист [{sheet_name}], строка {row_number} обновлена: {result.get('updatedCells')} ячеек изменено.")
    except Exception as e:
        print(f"Ошибка при обновлении статуса в листе {sheet_name}: {e}")

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Ошибка при рендеринге шаблона: {e}")
        return str(e), 500

@app.route('/health')
def health_check():
    return 'OK', 200

@app.route('/api/posts')
def get_posts():
    try:
        all_posts = []
        for sheet_name in CHANNELS_SHEETS.values():
            posts = get_posts_from_sheet(sheet_name)
            all_posts.extend(posts)
        return jsonify(all_posts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_status', methods=['POST'])
def update_status():
    try:
        data = request.json
        sheet_name = CHANNELS_SHEETS[data['channel_id']]
        range_to_update = f"'{sheet_name}'!A{data['row']}:F{data['row']}"
        values = [[
            data['date'],
            data['time'],
            data['photo'],
            data['text'],
            data['editor_confirm'],
            data['state']
        ]]
        
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_to_update,
            valueInputOption='RAW',
            body={'values': values}
        ).execute()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/publish_now', methods=['POST'])
def publish_now():
    try:
        data = request.json
        channel_id = data['channel_id']
        text = data['text']
        photo = data.get('photo')
        
        if photo:
            run_async(bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=text
            ))
        else:
            run_async(bot.send_message(
                chat_id=channel_id,
                text=text
            ))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def background_tasks():
    while True:
        socketio.sleep(60)  # Обновление каждую минуту
        try:
            all_posts = []
            for sheet_name in CHANNELS_SHEETS.values():
                posts = get_posts_from_sheet(sheet_name)
                all_posts.extend(posts)
            socketio.emit('posts_update', {'posts': all_posts})
        except Exception as e:
            print(f"Ошибка в фоновой задаче: {e}")

def publish_posts_all_channels():
    now = datetime.now()
    print(f"Текущее время: {now}")
    for channel_id, sheet_name in CHANNELS_SHEETS.items():
        print(f"Обработка листа '{sheet_name}' для канала '{channel_id}'...")
        posts = get_posts_from_sheet(sheet_name)
        for idx, post in enumerate(posts):
            if post['editor_confirm'] and post['time'] <= now and post['state'] == 'ожидает':
                try:
                    if post['photo']:
                        run_async(bot.send_photo(
                            chat_id=channel_id,
                            photo=post['photo'],
                            caption=post['text']
                        ))
                    else:
                        run_async(bot.send_message(
                            chat_id=channel_id,
                            text=post['text']
                        ))
                    print(f"[{datetime.now()}] Опубликовано в {channel_id}: {post['text']}")
                    update_post_status(sheet_name, idx, new_status="выложен")
                except Exception as e:
                    print(f"Ошибка при публикации для канала {channel_id}: {e}")

# Запуск фоновых задач
socketio.start_background_task(background_tasks)

# Запуск планировщика для автоматической публикации
scheduler = BackgroundScheduler(timezone=pytz.utc)
scheduler.add_job(publish_posts_all_channels, 'interval', minutes=1)
scheduler.start()

if __name__ == '__main__':
    # Запуск Flask приложения
    port = int(os.environ.get('PORT', 5000))
    print(f"Запуск приложения на порту {port}")
    print(f"Путь к шаблонам: {TEMPLATE_DIR}")
    print(f"Путь к статическим файлам: {STATIC_DIR}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, use_reloader=False) 