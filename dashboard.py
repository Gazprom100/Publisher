from flask import Flask, render_template, jsonify, request
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

app = Flask(__name__)
socketio = SocketIO(app)

# Load configuration from environment variables
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1FUoF6V9whpPMfEml__rpqmGKPs5ohhLUI1s7D1N0SG8")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8006930667:AAHHpNFS3ySj8hzteC-mmg0YBtHnSf8jREs")

# Initialize Google Sheets service
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

# Initialize Telegram bot
bot = Bot(token=TELEGRAM_TOKEN)

# Global event loop for async operations
global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)

def run_async(coro):
    return global_loop.run_until_complete(coro)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/posts')
def get_posts():
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="A2:F"
        ).execute()
        values = result.get('values', [])
        
        posts = []
        for row in values:
            if len(row) < 6:
                continue
            posts.append({
                'date': row[0],
                'time': row[1],
                'photo': row[2],
                'text': row[3],
                'editor_confirm': row[4],
                'state': row[5]
            })
        return jsonify(posts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_status', methods=['POST'])
def update_status():
    try:
        data = request.json
        range_to_update = f"A{data['row']}:F{data['row']}"
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
        socketio.sleep(60)  # Update every minute
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range="A2:F"
            ).execute()
            values = result.get('values', [])
            socketio.emit('posts_update', {'posts': values})
        except Exception as e:
            print(f"Error in background task: {e}")

# Запуск HTTP-сервера для Render.com
def start_http_server():
    port = int(os.environ.get("PORT", 8000))
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
    
    httpd = HTTPServer(('', port), SimpleHandler)
    print(f"HTTP-сервер запущен на порту {port}")
    httpd.serve_forever()

if __name__ == '__main__':
    # Запуск HTTP-сервера в отдельном потоке
    threading.Thread(target=start_http_server, daemon=True).start()
    
    # Запуск фоновых задач
    socketio.start_background_task(background_tasks)
    
    # Запуск планировщика для автоматической публикации
    scheduler = BackgroundScheduler(timezone=pytz.utc)
    scheduler.add_job(publish_posts_all_channels, 'interval', minutes=1)
    scheduler.start()
    
    # Запуск Flask приложения
    socketio.run(app, debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 