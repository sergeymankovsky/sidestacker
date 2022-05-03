import uuid
from flask import (
    Blueprint, render_template, session, redirect, url_for, request, current_app as app, g
)

from flask_socketio import emit, join_room, leave_room
from sidestacker.db import get_db
from . import socketio

bp = Blueprint('games', __name__)


def start_game(game_id, player_id):
    db = get_db()
    db.execute(
        'INSERT INTO games (id, player1_id) VALUES (?, ?)',
        (game_id, player_id)
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
        'SELECT id, player1_id, player2_id FROM games WHERE id = ?',
        (game_id,)
    )
    return cursor.fetchone()


def add_move(game_id, piece, row, col):
    db = get_db()
    db.execute(
        'INSERT INTO moves (game_id, piece, row, col) VALUES (?, ?, ?, ?)',
        (game_id, piece, row, col)
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


def winning_move(board, piece):
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
        start_game(session['game_id'], session['player_id'])
        return redirect(url_for('games.game', game_id=session['game_id']))

    if not session.get('player_id'):
        session['player_id'] = get_uuid()

    return render_template('index.html')


@bp.route('/games/<game_id>', methods=('GET', 'POST'))
def game(game_id):
    if request.method == 'POST':
        session.pop('game_id')
        emit('end', namespace='', room=game_id)
        return redirect(url_for('games.index'))
    session['game_id'] = game_id

    if not session.get('player_id'):
        session['player_id'] = get_uuid()

    game = get_game(game_id)
    if not game['player2_id']:
        join_game(session['game_id'], session['player_id'])

    session['piece'] = get_piece(game_id)
    g.opponent = other_piece(session['piece'])

    return render_template('game.html')


@socketio.on('connect')
def on_connect():
    game_id = session['game_id']
    join_room(game_id)

    game = get_game(game_id)
    if game['player2_id']:
        emit('join', room=game_id)

        moves = get_moves(game_id)
        for move in moves:
            emit('move', move, room=game_id)

        last_piece = moves[-1]['piece'] if moves else 2
        emit_turn(game_id, last_piece)


@socketio.on('disconnect')
def on_disconnect():
    leave_room(session['game_id'])


@socketio.on('move')
def on_move(move):
    game_id = session['game_id']
    move['piece'] = session['piece']
    add_move(game_id, move['piece'], move['row'], move['col'])
    emit('move', move, room=game_id)

    emit_turn(game_id, move['piece'])


def emit_turn(game_id, piece):
    board = get_board(game_id)
    if winning_move(board, piece):
        emit('finish', {'winner': piece}, room=game_id)
    else:
        emit('turn', {
            'turn': other_piece(piece),
            'availableMoves': avaiable_moves(game_id)
        }, room=game_id)
