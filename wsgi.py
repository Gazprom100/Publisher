import eventlet
eventlet.monkey_patch()

import os
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from dashboard import app, socketio
    logger.info("Приложение успешно импортировано")
except Exception as e:
    logger.error(f"Ошибка при импорте приложения: {e}")
    raise

if __name__ == "__main__":
    try:
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"Запуск приложения на порту {port}")
        
        socketio.run(app, 
                    host='0.0.0.0', 
                    port=port,
                    debug=False,
                    use_reloader=False,
                    log_output=True,
                    websocket=True)
    except Exception as e:
        logger.error(f"Ошибка при запуске приложения: {e}")
        raise 