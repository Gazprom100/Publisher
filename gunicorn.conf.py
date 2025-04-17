import multiprocessing
import os

# Worker settings
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2
worker_class = 'eventlet'
worker_connections = 1000

# Timeouts
timeout = 120
keepalive = 5
graceful_timeout = 120

# Logging settings
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Binding settings
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Security settings
limit_request_line = 0
limit_request_fields = 0

# Proxy settings
forwarded_allow_ips = '*'
proxy_allow_ips = '*'

# SSL settings (uncomment if needed)
# keyfile = 'ssl/key.pem'
# certfile = 'ssl/cert.pem'

# Additional settings
preload_app = True
reload = False

# WebSocket optimizations
worker_tmp_dir = '/dev/shm'
max_requests = 1000
max_requests_jitter = 50

# Настройки для работы за прокси
# forwarded_allow_ips = '*'
# proxy_allow_ips = '*'

# SSL настройки (закомментированы, раскомментировать при необходимости)
# keyfile = 'ssl/key.pem'
# certfile = 'ssl/cert.pem'

# Дополнительные настройки
# preload_app = True
# reload = False  # Отключаем автоперезагрузку в продакшене

# Настройки для работы с WebSocket
# worker_class = "eventlet"
# workers = multiprocessing.cpu_count() * 2 + 1
# threads = workers * 2

# Настройки для отладки
# reload_engine = "auto"

# Настройки для работы с Unix-сокетами
# bind = "0.0.0.0:$PORT" 