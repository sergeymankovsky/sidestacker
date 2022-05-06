from random import choice
from itertools import chain
import uuid
from flask import (
    Blueprint, render_template, session, redirect, url_for, request,
    current_app as app, g
)

from flask_socketio import emit, join_room, leave_room
from sidestacker.db import get_db
from . import socketio

bp = Blueprint('games', __name__)


def start_game(game_id, player_id, opponent):
    db = get_db()
    db.execute(
        'INSERT INTO games (id, player1_id, opponent) VALUES (?, ?, ?)',
        (game_id, player_id, opponent)
    )
    db.commit()


def join_game(game_id, player_id):
    db = get_db()
    db.execute(
        'UPDATE games SET player2_id = ? '
        'WHERE id = ? AND player1_id != ? AND player2_id IS NULL',
        (player_id, game_id, player_id)
    )
    db.commit()


def get_game(game_id):
    db = get_db()
    cursor = db.execute(
        'SELECT id, player1_id, player2_id, opponent FROM games WHERE id = ?',
        (game_id,)
    )
    return cursor.fetchone()


def add_move(game_id, move):
    db = get_db()
    db.execute(
        'INSERT INTO moves (game_id, piece, row, col) VALUES (?, ?, ?, ?)',
        (game_id, move['piece'], move['row'], move['col'])
    )
    db.commit()


def get_moves(game_id):
    db = get_db()
    cursor = db.execute(
        'SELECT game_id, piece, row, col FROM moves WHERE game_id = ?',
        (game_id,)
    )
    return cursor.fetchall()


def get_uuid():
    return str(uuid.uuid4())


def get_piece(game_id):
    game = get_game(game_id)
    if (session['player_id'] == game['player1_id']):
        return 1
    if (session['player_id'] == game['player2_id']):
        return 2
    return None


def get_board(game_id):
    moves = get_moves(game_id)
    board = [[0] * app.config['BOARD_COLS']
             for _ in range(app.config['BOARD_ROWS'])]
    for move in moves:
        board[move['row']][move['col']] = move['piece']
    return board


def avaiable_moves(game_id):
    board = get_board(game_id)
    result = []
    for row in board:
        min_col = row.index(0) if 0 in row else -1
        if min_col != -1:
            max_col = max(i for i, col in enumerate(row) if col == 0)
            result.append([min_col, max_col])
        else:
            result.append([])
    return result


def bot_move(game_id):
    moves = avaiable_moves(game_id)
    moves = [[(i, r[0]), (i, r[1])] for i, r in enumerate(moves) if r]
    moves = list(chain(*moves))
    return choice(moves) if moves else None


def winning_move(game_id, piece):
    board = get_board(game_id)
    # Check horizontal
    for c in range(app.config['BOARD_COLS'] - 3):
        for r in range(app.config['BOARD_ROWS']):
            if (board[r][c] == piece and
                    board[r][c + 1] == piece and
                    board[r][c + 2] == piece and
                    board[r][c + 3] == piece):
                return True
    # Check vertical
    for c in range(app.config['BOARD_COLS']):
        for r in range(app.config['BOARD_ROWS'] - 3):
            if (board[r][c] == piece and
                    board[r + 1][c] == piece and
                    board[r + 2][c] == piece and
                    board[r + 3][c] == piece):
                return True
    # Check diagonal 1
    for c in range(app.config['BOARD_COLS'] - 3):
        for r in range(app.config['BOARD_ROWS'] - 3):
            if (board[r][c] == piece and
                    board[r + 1][c + 1] == piece and
                    board[r + 2][c + 2] == piece and
                    board[r + 3][c + 3] == piece):
                return True
    # Check diagonal 2
    for c in range(app.config['BOARD_COLS'] - 3):
        for r in range(3, app.config['BOARD_ROWS']):
            if (board[r][c] == piece and
                    board[r - 1][c + 1] == piece and
                    board[r - 2][c + 2] == piece and
                    board[r - 3][c + 3] == piece):
                return True
    return False


def other_piece(piece):
    return 2 if piece == 1 else 1


@bp.route('/', methods=('GET', 'POST'))
def index():
    if request.method == 'POST':
        session['game_id'] = get_uuid()
        opponent = request.form['opponent']
        start_game(session['game_id'], session['player_id'], opponent)
        return redirect(url_for('games.game', game_id=session['game_id']))

    if not session.get('player_id'):
        session['player_id'] = get_uuid()

    return render_template('index.html')


@bp.route('/games/<game_id>', methods=('GET', 'POST'))
def game(game_id):
    if request.method == 'POST':
        session.pop('game_id', None)
        emit('end', namespace='', room=game_id)
        return redirect(url_for('games.index'))
    session['game_id'] = game_id

    if not session.get('player_id'):
        session['player_id'] = get_uuid()

    game = get_game(game_id)
    if not game['player2_id'] and game['opponent'] == 'friend':
        join_game(session['game_id'], session['player_id'])

    session['piece'] = get_piece(game_id)
    g.opponent = other_piece(session['piece'])

    return render_template('game.html')


@socketio.on('connect')
def on_connect():
    game_id = session['game_id']
    join_room(game_id)

    game = get_game(game_id)
    if game['player2_id'] or game['opponent'] == 'bot':
        emit('join', room=game_id)

        moves = get_moves(game_id)
        for move in moves:
            send_update(game_id, move)
        if not moves:
            emit('update', {
                'turn': 1,
                'availableMoves': avaiable_moves(game_id)
            }, room=game_id)


@socketio.on('disconnect')
def on_disconnect():
    leave_room(session['game_id'])


@socketio.on('move')
def on_move(move):
    game_id = session['game_id']
    move['piece'] = session['piece']
    add_move(game_id, move)
    send_update(game_id, move)

    game = get_game(game_id)
    is_winning = winning_move(game_id, move['piece'])
    if game['opponent'] == 'bot' and not is_winning:
        make_bot_move(game_id, other_piece(move['piece']))


def make_bot_move(game_id, bot_piece):
    row, col = bot_move(game_id)
    move = {'piece': bot_piece, 'row': row, 'col': col}
    add_move(game_id, move)
    send_update(game_id, move)


def send_update(game_id, move):
    emit('update', {
        'move': move,
        'turn': other_piece(move['piece']),
        'availableMoves': avaiable_moves(game_id),
        'winningMove': winning_move(game_id, move['piece'])
    }, room=game_id)
