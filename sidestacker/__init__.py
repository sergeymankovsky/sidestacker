import os

from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        BOARD_ROWS=7,
        BOARD_COLS=7,
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'sidestacker.sqlite'),
        SOCK_SERVER_OPTIONS={'ping_interval': 25}
    )

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import db
    db.init_app(app)

    from . import games
    app.register_blueprint(games.bp)

    socketio.init_app(app)
    return app
