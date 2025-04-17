from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO
import json
import os
from datetime import datetime, timedelta
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import threading
import asyncio
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler
from gevent import monkey
from collections import defaultdict
import pandas as pd
from typing import Dict, List, Any
import logging
from telegram.error import TelegramError
import requests
from PIL import Image
from io import BytesIO
import hashlib
import redis
import plotly.graph_objects as go
import plotly.utils
from urllib.parse import urlparse
monkey.patch_all()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация Redis для кэширования
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(REDIS_URL)

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
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins='*')

# Загрузка конфигурации из переменных окружения
SERVICE_ACCOUNT_INFO = os.getenv("SERVICE_ACCOUNT_INFO")
if SERVICE_ACCOUNT_INFO:
    SERVICE_ACCOUNT_DICT = json.loads(SERVICE_ACCOUNT_INFO)
else:
    SERVICE_ACCOUNT_DICT = None

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1FUoF6V9whpPMfEml__rpqmGKPs5ohhLUI1s7D1N0SG8")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8006930667:AAHHpNFS3ySj8hzteC-mmg0YBtHnSf8jREs")

# Конфигурация каналов
CHANNELS_SHEETS = {
    "@KConsult_ing": "K.Consulting",
    "@Vegzzzbaj": "Vegzzzbaj"
}

# Инициализация сервиса Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

if SERVICE_ACCOUNT_DICT:
    credentials = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_DICT, scopes=SCOPES)
else:
    try:
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
    except FileNotFoundError:
        print("ВНИМАНИЕ: Файл service_account.json не найден и SERVICE_ACCOUNT_INFO не установлен!")
        credentials = None

if credentials:
    service = build('sheets', 'v4', credentials=credentials)
else:
    service = None
    print("Google Sheets API не инициализирован из-за отсутствия учетных данных")

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
    if not service:
        return 'Google Sheets API не инициализирован', 500
    return 'OK', 200

@app.route('/api/posts')
def get_posts():
    if not service:
        return jsonify({'error': 'Google Sheets API не инициализирован'}), 500
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

def get_analytics_data() -> Dict[str, Any]:
    """Получение аналитических данных по публикациям"""
    all_posts = []
    for channel_id, sheet_name in CHANNELS_SHEETS.items():
        posts = get_posts_from_sheet(sheet_name)
        for post in posts:
            post['channel'] = channel_id
        all_posts.extend(posts)
    
    # Конвертируем в pandas DataFrame для удобного анализа
    df = pd.DataFrame(all_posts)
    
    # Статистика по каналам
    channel_stats = defaultdict(lambda: {'total': 0, 'published': 0, 'waiting': 0, 'error': 0})
    for post in all_posts:
        channel = post['channel']
        channel_stats[channel]['total'] += 1
        if post['state'] == 'выложен':
            channel_stats[channel]['published'] += 1
        elif post['state'] == 'ожидает':
            channel_stats[channel]['waiting'] += 1
        else:
            channel_stats[channel]['error'] += 1
    
    # Статистика по времени публикации
    now = datetime.now()
    time_stats = {
        'today': len([p for p in all_posts if p['time'].date() == now.date()]),
        'week': len([p for p in all_posts if p['time'].date() >= (now - timedelta(days=7)).date()]),
        'month': len([p for p in all_posts if p['time'].date() >= (now - timedelta(days=30)).date()])
    }
    
    # Статистика по типам контента
    content_stats = {
        'with_photo': len([p for p in all_posts if p.get('photo')]),
        'text_only': len([p for p in all_posts if not p.get('photo')])
    }
    
    # График публикаций по часам
    if not df.empty and 'time' in df.columns:
        df['hour'] = df['time'].apply(lambda x: x.hour)
        posts_by_hour = df['hour'].value_counts().sort_index().to_dict()
    else:
        posts_by_hour = {}
    
    return {
        'channel_stats': channel_stats,
        'time_stats': time_stats,
        'content_stats': content_stats,
        'posts_by_hour': posts_by_hour,
        'total_posts': len(all_posts)
    }

@app.route('/api/analytics')
def get_analytics():
    """API endpoint для получения аналитических данных"""
    try:
        return jsonify(get_analytics_data())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/channel-health')
def get_channel_health():
    """Проверка здоровья каналов"""
    health_data = {}
    for channel_id in CHANNELS_SHEETS.keys():
        try:
            chat = run_async(bot.get_chat(channel_id))
            health_data[channel_id] = {
                'status': 'active',
                'title': chat.title,
                'members_count': chat.get_member_count() if hasattr(chat, 'get_member_count') else 'N/A',
                'last_checked': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            health_data[channel_id] = {
                'status': 'error',
                'error': str(e),
                'last_checked': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    return jsonify(health_data)

@app.route('/api/schedule-preview')
def get_schedule_preview():
    """Получение предварительного просмотра расписания публикаций"""
    try:
        now = datetime.now()
        end_date = now + timedelta(days=7)
        scheduled_posts = []
        
        for channel_id, sheet_name in CHANNELS_SHEETS.items():
            posts = get_posts_from_sheet(sheet_name)
            for post in posts:
                if post['state'] == 'ожидает' and now <= post['time'] <= end_date:
                    scheduled_posts.append({
                        'channel': channel_id,
                        'time': post['time'].strftime('%Y-%m-%d %H:%M'),
                        'text': post['text'][:100] + '...' if len(post['text']) > 100 else post['text'],
                        'has_photo': bool(post.get('photo'))
                    })
        
        return jsonify(sorted(scheduled_posts, key=lambda x: x['time']))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def cache_key(prefix: str, *args) -> str:
    """Генерирует ключ кэша на основе префикса и аргументов"""
    key_parts = [prefix] + [str(arg) for arg in args]
    return ':'.join(key_parts)

def cached(prefix: str, timeout: int = 300):
    """Декоратор для кэширования результатов функций"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            key = cache_key(prefix, *args, *kwargs.values())
            result = redis_client.get(key)
            if result:
                return json.loads(result)
            result = func(*args, **kwargs)
            redis_client.setex(key, timeout, json.dumps(result))
            return result
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

def validate_image_url(url: str) -> bool:
    """Проверяет валидность URL изображения и его размер"""
    try:
        response = requests.head(url, timeout=5)
        if response.status_code != 200:
            return False
        
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            return False
        
        content_length = int(response.headers.get('content-length', 0))
        if content_length > 5 * 1024 * 1024:  # 5MB limit
            return False
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при проверке изображения {url}: {e}")
        return False

@app.route('/api/validate-image', methods=['POST'])
def validate_image():
    """API endpoint для валидации URL изображения"""
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL не указан'}), 400
    
    is_valid = validate_image_url(url)
    return jsonify({'valid': is_valid})

def get_post_statistics(days: int = 30) -> Dict[str, Any]:
    """Получает статистику постов за указанный период"""
    stats = defaultdict(int)
    now = datetime.now()
    start_date = now - timedelta(days=days)
    
    for channel_id, sheet_name in CHANNELS_SHEETS.items():
        posts = get_posts_from_sheet(sheet_name)
        for post in posts:
            if start_date <= post['time'] <= now:
                stats['total'] += 1
                if post['state'] == 'выложен':
                    stats['published'] += 1
                if post['photo']:
                    stats['with_photo'] += 1
                
                # Статистика по времени публикации
                hour = post['time'].hour
                if 6 <= hour < 12:
                    stats['morning'] += 1
                elif 12 <= hour < 18:
                    stats['afternoon'] += 1
                elif 18 <= hour < 24:
                    stats['evening'] += 1
                else:
                    stats['night'] += 1
    
    return stats

@app.route('/api/post-statistics')
def get_post_statistics_api():
    """API endpoint для получения статистики постов"""
    days = request.args.get('days', default=30, type=int)
    stats = get_post_statistics(days)
    return jsonify(stats)

def get_engagement_metrics(channel_id: str) -> Dict[str, float]:
    """Получает метрики вовлеченности для канала"""
    try:
        # Получаем информацию о канале через Telegram API
        chat = run_async(bot.get_chat(channel_id))
        member_count = chat.member_count if hasattr(chat, 'member_count') else 0
        
        # Анализируем последние посты
        posts = get_posts_from_sheet(CHANNELS_SHEETS[channel_id])
        recent_posts = [p for p in posts if p['state'] == 'выложен' and 
                       p['time'] >= datetime.now() - timedelta(days=7)]
        
        total_posts = len(recent_posts)
        if total_posts == 0:
            return {
                'posts_per_day': 0,
                'member_count': member_count,
                'estimated_reach': 0
            }
        
        posts_per_day = total_posts / 7
        estimated_reach = member_count * 0.3  # Примерная оценка охвата
        
        return {
            'posts_per_day': round(posts_per_day, 2),
            'member_count': member_count,
            'estimated_reach': round(estimated_reach)
        }
    except Exception as e:
        logger.error(f"Ошибка при получении метрик для {channel_id}: {e}")
        return {
            'posts_per_day': 0,
            'member_count': 0,
            'estimated_reach': 0
        }

@app.route('/api/engagement-metrics')
def get_engagement_metrics_api():
    """API endpoint для получения метрик вовлеченности"""
    metrics = {}
    for channel_id in CHANNELS_SHEETS.keys():
        metrics[channel_id] = get_engagement_metrics(channel_id)
    return jsonify(metrics)

def generate_content_distribution_chart() -> Dict:
    """Генерирует график распределения контента"""
    stats = defaultdict(int)
    for sheet_name in CHANNELS_SHEETS.values():
        posts = get_posts_from_sheet(sheet_name)
        for post in posts:
            if post['photo']:
                stats['С фото'] += 1
            else:
                stats['Только текст'] += 1
    
    fig = go.Figure(data=[go.Pie(
        labels=list(stats.keys()),
        values=list(stats.values()),
        hole=.3
    )])
    
    fig.update_layout(
        title="Распределение типов контента",
        showlegend=True,
        height=400,
        margin=dict(t=50, l=0, r=0, b=0)
    )
    
    return json.loads(json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder))

@app.route('/api/content-distribution')
def get_content_distribution():
    """API endpoint для получения графика распределения контента"""
    return jsonify(generate_content_distribution_chart())

def analyze_post_performance(post: Dict) -> Dict[str, Any]:
    """Анализирует эффективность поста"""
    score = 0
    feedback = []
    
    # Анализ длины текста
    text_length = len(post['text'])
    if text_length < 100:
        score -= 1
        feedback.append("Текст слишком короткий")
    elif text_length > 2000:
        score -= 1
        feedback.append("Текст слишком длинный")
    else:
        score += 1
    
    # Анализ наличия медиа
    if post['photo']:
        score += 1
    else:
        feedback.append("Добавьте фото для лучшего восприятия")
    
    # Анализ времени публикации
    hour = post['time'].hour
    if 9 <= hour <= 21:
        score += 1
    else:
        feedback.append("Рекомендуется публиковать посты с 9:00 до 21:00")
    
    return {
        'score': score,
        'feedback': feedback,
        'optimization_tips': [
            "Используйте эмодзи для привлечения внимания",
            "Добавьте призыв к действию",
            "Структурируйте текст с помощью абзацев"
        ] if score < 2 else []
    }

@app.route('/api/analyze-post', methods=['POST'])
def analyze_post_api():
    """API endpoint для анализа поста"""
    data = request.json
    if not data:
        return jsonify({'error': 'Данные не предоставлены'}), 400
    
    analysis = analyze_post_performance(data)
    return jsonify(analysis)

def get_post_suggestions() -> List[Dict[str, str]]:
    """Генерирует предложения по улучшению контента"""
    return [
        {
            'type': 'timing',
            'suggestion': 'Оптимальное время публикации: 12:00-14:00 и 19:00-21:00',
            'importance': 'high'
        },
        {
            'type': 'content',
            'suggestion': 'Добавляйте больше визуального контента',
            'importance': 'medium'
        },
        {
            'type': 'engagement',
            'suggestion': 'Используйте опросы и интерактивные элементы',
            'importance': 'high'
        }
    ]

@app.route('/api/post-suggestions')
def get_post_suggestions_api():
    """API endpoint для получения предложений по улучшению контента"""
    return jsonify(get_post_suggestions())

if __name__ == '__main__':
    # Запуск Flask приложения
    port = int(os.environ.get('PORT', 5000))
    print(f"Запуск приложения на порту {port}")
    print(f"Путь к шаблонам: {TEMPLATE_DIR}")
    print(f"Путь к статическим файлам: {STATIC_DIR}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, use_reloader=False) 