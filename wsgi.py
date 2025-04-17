from gevent import monkey
monkey.patch_all()

from dashboard import app, socketio

if __name__ == "__main__":
    socketio.run(app) 