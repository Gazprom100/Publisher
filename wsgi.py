import eventlet
eventlet.monkey_patch()

from dashboard import app, socketio
import os

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, 
                host='0.0.0.0', 
                port=port,
                debug=False,
                use_reloader=False,
                log_output=True,
                websocket=True) 