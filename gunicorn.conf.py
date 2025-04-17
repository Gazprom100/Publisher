import multiprocessing
import os

# Настройки воркеров
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2
worker_class = 'eventlet'
worker_connections = 1000

# Таймауты
timeout = 120
keepalive = 5
graceful_timeout = 120

# Настройки логирования
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Настройки привязки
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Настройки безопасности
limit_request_line = 0
limit_request_fields = 0

# Настройки для работы за прокси
forwarded_allow_ips = '*'
proxy_allow_ips = '*'

# SSL настройки (закомментированы, раскомментировать при необходимости)
# keyfile = 'ssl/key.pem'
# certfile = 'ssl/cert.pem'

# Дополнительные настройки
preload_app = True
reload = False  # Отключаем автоперезагрузку в продакшене

# Настройки для работы с WebSocket
# worker_class = "eventlet"
# workers = multiprocessing.cpu_count() * 2 + 1
# threads = workers * 2

# Настройки для отладки
# reload_engine = "auto"

# Настройки для работы с Unix-сокетами
# bind = "0.0.0.0:$PORT" 