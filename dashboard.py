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
import eventlet
import sys
import signal

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
try:
    redis_client = redis.from_url(REDIS_URL)
    # Проверяем подключение
    redis_client.ping()
except redis.ConnectionError:
    logger.warning("Не удалось подключиться к Redis. Кэширование будет отключено.")
    redis_client = None

# Определяем базовый путь для шаблонов и статических файлов
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Создаем директории, если они не существуют
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Инициализация eventlet
eventlet.monkey_patch(all=False, socket=True, select=True, thread=True)

app = Flask(__name__, 
            template_folder=TEMPLATE_DIR,
            static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = os.urandom(24)

# Обновленные настройки Socket.IO
socketio = SocketIO(app, 
                   async_mode='eventlet',
                   cors_allowed_origins='*',
                   engineio_logger=True,
                   logger=True,
                   ping_timeout=60,
                   ping_interval=25,
                   max_http_buffer_size=1000000,
                   manage_session=True,  # Включаем управление сессиями
                   reconnection=True,    # Включаем автоматическое переподключение
                   reconnection_attempts=5,  # Количество попыток переподключения
                   reconnection_delay=1000,  # Задержка между попытками в миллисекундах
                   cookie=None)  # Отключаем использование cookie для сессий

@socketio.on_error_default
def default_error_handler(e):
    logger.error(f"Socket.IO error: {str(e)}")

@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")

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

# Инициализация планировщика
scheduler = BackgroundScheduler(
    daemon=True,
    timezone=pytz.utc,
    job_defaults={
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 60
    }
)

def background_tasks():
    """Фоновая задача для обновления данных через WebSocket"""
    while True:
        try:
            all_posts = []
            for sheet_name in CHANNELS_SHEETS.values():
                try:
                    posts = get_posts_from_sheet(sheet_name)
                    all_posts.extend(posts)
                except Exception as e:
                    logger.error(f"Ошибка при получении постов из листа {sheet_name}: {e}")
                    continue
            
            # Проверяем наличие активных клиентов перед отправкой
            if len(socketio.server.eio.sockets) > 0:
                socketio.emit('posts_update', {'posts': all_posts})
                logger.debug("Данные успешно отправлены через WebSocket")
            
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче WebSocket: {e}")
        finally:
            eventlet.sleep(60)  # Пауза между обновлениями

def publish_posts_all_channels():
    """Публикация запланированных постов"""
    try:
        now = datetime.now()
        logger.info(f"Запуск проверки публикаций в {now}")
        
        for channel_id, sheet_name in CHANNELS_SHEETS.items():
            try:
                posts = get_posts_from_sheet(sheet_name)
                for idx, post in enumerate(posts):
                    if post['editor_confirm'] and post['time'] <= now and post['state'].lower() == 'ожидает':
                        try:
                            # Добавляем задержку между публикациями
                            if idx > 0:
                                eventlet.sleep(2)
                                
                            logger.info(f"Попытка публикации в канал {channel_id}")
                            if post['photo']:
                                message = run_async(bot.send_photo(
                                    chat_id=channel_id,
                                    photo=post['photo'],
                                    caption=post['text']
                                ))
                            else:
                                message = run_async(bot.send_message(
                                    chat_id=channel_id,
                                    text=post['text']
                                ))
                            
                            if message:
                                logger.info(f"Успешная публикация в {channel_id}: {post['text'][:50]}...")
                                update_post_status(sheet_name, idx, new_status="выложен")
                            else:
                                logger.error(f"Не удалось получить подтверждение публикации для {channel_id}")
                                
                        except Exception as e:
                            logger.error(f"Ошибка при публикации в канал {channel_id}: {e}")
                            update_post_status(sheet_name, idx, new_status="ошибка")
            except Exception as e:
                logger.error(f"Ошибка при обработке канала {channel_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка в задаче публикации: {e}")

# Настройка и запуск планировщика
scheduler.add_job(
    publish_posts_all_channels,
    'interval',
    minutes=1,
    id='publish_posts_job',
    replace_existing=True
)

try:
    scheduler.start()
    logger.info("Планировщик успешно запущен")
except Exception as e:
    logger.error(f"Ошибка при запуске планировщика: {e}")

# Запуск фоновой задачи WebSocket
socketio.start_background_task(background_tasks)

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
    """Получение аналитических данных"""
    try:
        all_posts = []
        total_reach = 0
        active_channels = 0
        
        # Собираем данные по всем каналам
        for channel_id, sheet_name in CHANNELS_SHEETS.items():
            try:
                posts = get_posts_from_sheet(sheet_name)
                all_posts.extend(posts)
                
                # Проверяем активность канала (есть посты за последние 7 дней)
                recent_posts = [
                    post for post in posts 
                    if post['time'] >= datetime.now() - timedelta(days=7)
                ]
                if recent_posts:
                    active_channels += 1
                    
            except Exception as e:
                logger.error(f"Ошибка при получении данных для канала {channel_id}: {e}")
                continue
        
        # Считаем статистику
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        posts_today = len([
            post for post in all_posts 
            if post['time'].date() == now.date() and post['state'] == 'выложен'
        ])
        
        total_posts = len([post for post in all_posts if post['state'] == 'выложен'])
        
        # Готовим данные по активности
        activity_by_hour = {}
        for hour in range(24):
            activity_by_hour[str(hour)] = 0
            
        for post in all_posts:
            if post['state'] == 'выложен':
                hour = str(post['time'].hour)
                activity_by_hour[hour] += 1
        
        # Типы контента (пока просто наличие фото)
        posts_with_photo = len([post for post in all_posts if post['photo'] and post['state'] == 'выложен'])
        posts_without_photo = total_posts - posts_with_photo
        
        return jsonify({
            'success': True,
            'total_posts': total_posts,
            'posts_today': posts_today,
            'active_channels': active_channels,
            'total_reach': total_reach,
            'activity_by_hour': activity_by_hour,
            'posts_with_photo': posts_with_photo,
            'posts_without_photo': posts_without_photo
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении аналитики: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/channel-health')
def get_channel_health():
    try:
        channel_health = {}
        for channel_id, sheet_name in CHANNELS_SHEETS.items():
            try:
                # Получаем информацию о канале через Telegram API
                chat_info = run_async(bot.get_chat(channel_id))
                
                # Получаем посты канала
                posts = get_posts_from_sheet(sheet_name)
                
                # Рассчитываем статистику
                total_posts = len(posts)
                posts_last_week = len([p for p in posts if 
                    (datetime.now() - p['time']).days <= 7])
                
                # Собираем информацию о канале
                channel_health[channel_id] = {
                    'title': chat_info.title,
                    'member_count': chat_info.member_count if hasattr(chat_info, 'member_count') else 0,
                    'total_posts': total_posts,
                    'posts_per_week': posts_last_week,
                    'posts_with_photo': len([p for p in posts if p['photo']]),
                    'status': 'active' if posts_last_week > 0 else 'inactive',
                    'last_post_time': max([p['time'] for p in posts]) if posts else None
                }
            except TelegramError as e:
                logger.error(f"Ошибка при получении данных канала {channel_id}: {e}")
                channel_health[channel_id] = {
                    'error': str(e),
                    'status': 'error'
                }
                
        return jsonify(channel_health)
    except Exception as e:
        logger.error(f"Ошибка при получении данных о каналах: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedule-preview')
def get_schedule_preview():
    try:
        all_posts = []
        now = datetime.now()
        
        for channel_id, sheet_name in CHANNELS_SHEETS.items():
            posts = get_posts_from_sheet(sheet_name)
            for post in posts:
                if post['time'] > now and post['state'].lower() == 'ожидает':
                    post['channel'] = channel_id
                    all_posts.append(post)
        
        # Сортируем по времени и берем ближайшие 5 постов
        upcoming_posts = sorted(all_posts, key=lambda x: x['time'])[:5]
        
        return jsonify(upcoming_posts)
    except Exception as e:
        logger.error(f"Ошибка при получении предварительного расписания: {e}")
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
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'valid': False, 'error': 'URL не указан'}), 400
            
        try:
            response = requests.get(url)
            img = Image.open(BytesIO(response.content))
            
            # Проверяем размер файла (не более 5MB)
            file_size = len(response.content)
            if file_size > 5 * 1024 * 1024:  # 5MB в байтах
                return jsonify({'valid': False, 'error': 'Размер файла превышает 5MB'})
                
            # Проверяем формат
            valid_formats = {'JPEG', 'PNG', 'GIF'}
            if img.format not in valid_formats:
                return jsonify({'valid': False, 'error': 'Неподдерживаемый формат изображения'})
                
            return jsonify({'valid': True, 'format': img.format, 'size': file_size})
            
        except Exception as e:
            return jsonify({'valid': False, 'error': str(e)})
            
    except Exception as e:
        logger.error(f"Ошибка при валидации изображения: {e}")
        return jsonify({'error': str(e)}), 500

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
def analyze_post():
    try:
        data = request.json
        text = data.get('text', '')
        photo = data.get('photo')
        post_time = data.get('time')
        
        analysis = {
            'score': 0,
            'feedback': [],
            'optimization_tips': []
        }
        
        # Анализ длины текста
        text_length = len(text)
        if text_length < 50:
            analysis['feedback'].append('Текст слишком короткий')
            analysis['optimization_tips'].append('Добавьте больше информации, минимум 50 символов')
        elif text_length > 1500:
            analysis['feedback'].append('Текст слишком длинный')
            analysis['optimization_tips'].append('Сократите текст до 1500 символов для лучшего восприятия')
        else:
            analysis['score'] += 1
            analysis['feedback'].append('Оптимальная длина текста')
            
        # Анализ наличия фото
        if photo:
            analysis['score'] += 1
            analysis['feedback'].append('Наличие изображения повышает вовлеченность')
        else:
            analysis['optimization_tips'].append('Добавьте изображение для повышения вовлеченности')
            
        # Анализ времени публикации
        if post_time:
            post_hour = datetime.fromisoformat(post_time).hour
            if 9 <= post_hour <= 21:
                analysis['score'] += 1
                analysis['feedback'].append('Оптимальное время публикации')
            else:
                analysis['optimization_tips'].append('Рекомендуется публиковать посты с 9:00 до 21:00')
                
        return jsonify(analysis)
        
    except Exception as e:
        logger.error(f"Ошибка при анализе поста: {e}")
        return jsonify({'error': str(e)}), 500

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

# Добавляем новые эндпоинты для управления каналами
@app.route('/api/channels', methods=['GET'])
def get_channels():
    """Получение списка каналов"""
    try:
        channels_info = {}
        for channel_id, sheet_name in CHANNELS_SHEETS.items():
            try:
                # Получаем информацию о канале
                chat_info = run_async(bot.get_chat(channel_id))
                channels_info[channel_id] = {
                    'sheet_name': sheet_name,
                    'title': chat_info.title,
                    'type': chat_info.type,
                    'member_count': chat_info.member_count if hasattr(chat_info, 'member_count') else 0,
                    'status': 'active'
                }
            except Exception as e:
                channels_info[channel_id] = {
                    'sheet_name': sheet_name,
                    'error': str(e),
                    'status': 'error'
                }
        return jsonify(channels_info)
    except Exception as e:
        logger.error(f"Ошибка при получении списка каналов: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels', methods=['POST'])
def add_channel():
    """Добавление нового канала"""
    try:
        data = request.json
        channel_id = data.get('channel_id')
        sheet_name = data.get('sheet_name')
        
        if not channel_id or not sheet_name:
            return jsonify({'error': 'Необходимо указать channel_id и sheet_name'}), 400
            
        # Проверяем существование канала
        try:
            chat_info = run_async(bot.get_chat(channel_id))
        except Exception as e:
            return jsonify({'error': f'Канал не найден или бот не имеет доступа: {str(e)}'}), 400
            
        # Проверяем права бота в канале
        try:
            bot_member = run_async(bot.get_chat_member(channel_id, bot.id))
            if not bot_member.can_post_messages:
                return jsonify({'error': 'Бот не имеет прав на публикацию в канале'}), 400
        except Exception as e:
            return jsonify({'error': f'Ошибка проверки прав бота: {str(e)}'}), 400
            
        # Добавляем канал в конфигурацию
        CHANNELS_SHEETS[channel_id] = sheet_name
        
        # Создаем лист в Google Sheets, если его нет
        try:
            service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=f"'{sheet_name}'!A1"
            ).execute()
        except Exception:
            # Создаем новый лист
            try:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=SPREADSHEET_ID,
                    body={
                        'requests': [{
                            'addSheet': {
                                'properties': {
                                    'title': sheet_name,
                                    'gridProperties': {
                                        'rowCount': 1000,
                                        'columnCount': 6
                                    }
                                }
                            }
                        }]
                    }
                ).execute()
                
                # Добавляем заголовки
                service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"'{sheet_name}'!A1:F1",
                    valueInputOption='RAW',
                    body={
                        'values': [['Дата', 'Время', 'Фото', 'Текст', 'Подтверждено', 'Статус']]
                    }
                ).execute()
            except Exception as e:
                return jsonify({'error': f'Ошибка создания листа: {str(e)}'}), 500
                
        return jsonify({
            'success': True,
            'channel': {
                'id': channel_id,
                'title': chat_info.title,
                'sheet_name': sheet_name
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении канала: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels/<channel_id>', methods=['DELETE'])
def delete_channel(channel_id):
    """Удаление канала"""
    try:
        if channel_id not in CHANNELS_SHEETS:
            return jsonify({'error': 'Канал не найден'}), 404
            
        sheet_name = CHANNELS_SHEETS[channel_id]
        del CHANNELS_SHEETS[channel_id]
        
        return jsonify({'success': True, 'message': f'Канал {channel_id} удален'})
    except Exception as e:
        logger.error(f"Ошибка при удалении канала: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels/<channel_id>/feed')
def get_channel_feed(channel_id):
    """Получение ленты канала"""
    try:
        if channel_id not in CHANNELS_SHEETS:
            return jsonify({'error': 'Канал не найден'}), 404
            
        sheet_name = CHANNELS_SHEETS[channel_id]
        posts = get_posts_from_sheet(sheet_name)
        
        # Разделяем посты на прошлые и будущие
        now = datetime.now()
        past_posts = []
        future_posts = []
        
        for post in posts:
            post_data = {
                'time': post['time'].isoformat(),
                'photo': post['photo'],
                'text': post['text'],
                'editor_confirm': post['editor_confirm'],
                'state': post['state']
            }
            
            if post['time'] <= now:
                past_posts.append(post_data)
            else:
                future_posts.append(post_data)
                
        # Сортируем посты
        past_posts.sort(key=lambda x: x['time'], reverse=True)  # От новых к старым
        future_posts.sort(key=lambda x: x['time'])  # От ближайших к дальним
        
        return jsonify({
            'channel_id': channel_id,
            'past_posts': past_posts,
            'future_posts': future_posts
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении ленты канала {channel_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels/<channel_id>/posts', methods=['POST'])
def create_channel_post(channel_id):
    """Создание нового поста в канале"""
    try:
        if channel_id not in CHANNELS_SHEETS:
            return jsonify({'error': 'Канал не найден'}), 404
            
        data = request.json
        sheet_name = CHANNELS_SHEETS[channel_id]
        
        # Получаем последнюю строку в таблице
        range_name = get_range_name(sheet_name)
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        
        next_row = len(result.get('values', [])) + 2  # +2 because of header row
        
        # Форматируем дату и время
        post_time = datetime.fromisoformat(data['time'])
        date_str = post_time.strftime('%d.%m.%Y')
        time_str = post_time.strftime('%H:%M')
        
        # Добавляем новую строку
        range_to_update = f"'{sheet_name}'!A{next_row}:F{next_row}"
        values = [[
            date_str,
            time_str,
            data.get('photo', ''),
            data.get('text', ''),
            'TRUE' if data.get('editor_confirm') else 'FALSE',
            'ожидает'
        ]]
        
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_to_update,
            valueInputOption='RAW',
            body={'values': values}
        ).execute()
        
        return jsonify({
            'success': True,
            'message': 'Пост создан',
            'row': next_row
        })
        
    except Exception as e:
        logger.error(f"Ошибка при создании поста в канале {channel_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels/<channel_id>/posts/<int:row>', methods=['PUT'])
def update_channel_post(channel_id, row):
    """Обновление поста в канале"""
    try:
        if channel_id not in CHANNELS_SHEETS:
            return jsonify({'error': 'Канал не найден'}), 404
            
        data = request.json
        sheet_name = CHANNELS_SHEETS[channel_id]
        
        # Форматируем дату и время если они предоставлены
        if 'time' in data:
            post_time = datetime.fromisoformat(data['time'])
            date_str = post_time.strftime('%d.%m.%Y')
            time_str = post_time.strftime('%H:%M')
        else:
            # Получаем текущие значения
            range_name = f"'{sheet_name}'!A{row}:B{row}"
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name
            ).execute()
            values = result.get('values', [[]])[0]
            date_str = values[0] if len(values) > 0 else ''
            time_str = values[1] if len(values) > 1 else ''
        
        # Обновляем строку
        range_to_update = f"'{sheet_name}'!A{row}:F{row}"
        values = [[
            date_str,
            time_str,
            data.get('photo', ''),
            data.get('text', ''),
            'TRUE' if data.get('editor_confirm') else 'FALSE',
            data.get('state', 'ожидает')
        ]]
        
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_to_update,
            valueInputOption='RAW',
            body={'values': values}
        ).execute()
        
        return jsonify({
            'success': True,
            'message': 'Пост обновлен'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении поста в канале {channel_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-text', methods=['POST'])
def generate_post_text():
    """Генерация текста для поста"""
    try:
        data = request.json
        prompt = data.get('prompt', '')
        
        # Здесь можно добавить интеграцию с GPT или другим генератором текста
        # Пока возвращаем заглушку
        generated_text = "Сгенерированный текст поста..."
        
        return jsonify({
            'success': True,
            'text': generated_text
        })
        
    except Exception as e:
        logger.error(f"Ошибка при генерации текста: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    try:
        # Проверяем, не занят ли порт
        port = int(os.environ.get('PORT', 10000))
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('0.0.0.0', port))
        if result == 0:
            logger.error(f"Порт {port} уже используется")
            # Пробуем использовать следующий доступный порт
            port += 1
            while result == 0 and port < 65535:
                result = sock.connect_ex(('0.0.0.0', port))
                if result == 0:
                    port += 1
        sock.close()
        
        logger.info(f"Запуск приложения на порту {port}")
        logger.info(f"Путь к шаблонам: {TEMPLATE_DIR}")
        logger.info(f"Путь к статическим файлам: {STATIC_DIR}")
        
        # Устанавливаем обработчик сигналов для корректного завершения
        def signal_handler(sig, frame):
            logger.info("Получен сигнал завершения, останавливаем приложение...")
            socketio.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Запускаем приложение с обновленными настройками
        socketio.run(app, 
                    debug=False, 
                    host='0.0.0.0', 
                    port=port, 
                    use_reloader=False,
                    log_output=True,
                    websocket=True,
                    allow_upgrades=True,  # Разрешаем обновление соединения
                    ping_interval=25,     # Интервал пинга в секундах
                    ping_timeout=60)      # Таймаут пинга в секундах
    except Exception as e:
        logger.error(f"Ошибка при запуске приложения: {e}")
        raise 