from gevent import monkey
monkey.patch_all()

from dashboard import app, socketio
import os

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True) 