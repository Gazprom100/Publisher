import multiprocessing

# Настройки для работы с WebSocket
worker_class = "eventlet"
workers = multiprocessing.cpu_count() * 2 + 1
threads = workers * 2

# Таймауты
timeout = 120
keepalive = 5

# Логирование
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Настройки для работы с прокси
forwarded_allow_ips = '*'
proxy_allow_ips = '*'

# Настройки для WebSocket
worker_connections = 1000
worker_class = "eventlet"

# Настройки для SSL (если используется)
# keyfile = "path/to/keyfile"
# certfile = "path/to/certfile"

# Настройки для отладки
reload = False
reload_engine = "auto"

# Настройки для работы с Unix-сокетами
bind = "0.0.0.0:$PORT" 