from sidestacker import socketio, create_app


if __name__ == '__main__':
    socketio.run(create_app())
