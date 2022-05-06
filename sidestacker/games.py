from random import choice
import uuid
from flask import (
    Blueprint, render_template, session, redirect, url_for, request,
    current_app as app, g
)
import math
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


def copy_board(board):
    return [row.copy() for row in board]


def avaiable_moves(board):
    result = []
    for index, row in enumerate(board):
        min_col = row.index(0) if 0 in row else -1
        if min_col != -1:
            result.append((index, min_col))
            max_col = max(i for i, col in enumerate(row) if col == 0)
            if max_col != min_col:
                result.append((index, max_col))
    return result


def set_piece(board, move, piece):
    board[move[0]][move[1]] = piece


def score_window(window, piece):
    score = 0
    if window.count(piece) == 4:
        score += 100
    elif window.count(piece) == 3 and window.count(0) == 1:
        score += 5
    elif window.count(piece) == 2 and window.count(0) == 2:
        score += 2
    if window.count(other_piece(piece)) == 3 and window.count(0) == 1:
        score -= 4
    return score


def score_move(board, piece):
    center_col = app.config['BOARD_COLS'] // 2
    center_count = [row[center_col] for row in board].count(piece)
    score = center_count * 3

    for c in range(app.config['BOARD_COLS'] - 3):
        for r in range(app.config['BOARD_ROWS']):
            window = [board[r][c], board[r][c + 1], board[r][c + 2], board[r][c + 3]]
            score += score_window(window, piece)
    for c in range(app.config['BOARD_COLS']):
        for r in range(app.config['BOARD_ROWS'] - 3):
            window = [board[r][c], board[r + 1][c], board[r + 2][c], board[r + 3][c]]
            score += score_window(window, piece)
    for c in range(app.config['BOARD_COLS'] - 3):
        for r in range(app.config['BOARD_ROWS'] - 3):
            window = [board[r][c], board[r + 1][c + 1], board[r + 2][c + 2], board[r + 3][c + 3]]
            score += score_window(window, piece)
    for c in range(app.config['BOARD_COLS'] - 3):
        for r in range(3, app.config['BOARD_ROWS']):
            window = [board[r][c], board[r - 1][c + 1], board[r - 2][c + 2], board[r - 3][c + 3]]
            score += score_window(window, piece)

    return score


def is_terminal_move(board, bot_piece):
    return (winning_move(board, bot_piece) or
            winning_move(board, other_piece(bot_piece)) or
            not avaiable_moves(board))


def minimax(board, depth, alpha, beta, maximizing_player, bot_piece):
    player_piece = other_piece(bot_piece)
    moves = avaiable_moves(board)
    is_terminal = is_terminal_move(board, bot_piece)
    if depth == 0 or is_terminal:
        if is_terminal:
            if winning_move(board, bot_piece):
                return None, math.inf
            elif winning_move(board, player_piece):
                return None, -math.inf
            else:
                return None, 0
        else:
            return (None, score_move(board, bot_piece))
    if maximizing_player:
        value = -math.inf
        move = choice(moves)
        for m in moves:
            board_copy = copy_board(board)
            set_piece(board_copy, m, bot_piece)
            new_score = minimax(
                board_copy, depth - 1, alpha, beta, False, bot_piece)[1]
            if new_score > value:
                value = new_score
                move = m
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return move, value
    else:
        value = math.inf
        move = choice(moves)
        for m in moves:
            board_copy = copy_board(board)
            set_piece(board_copy, m, player_piece)
            new_score = minimax(
                board_copy, depth - 1, alpha, beta, True, bot_piece)[1]
            if new_score < value:
                value = new_score
                move = m
            beta = min(beta, value)
            if alpha >= beta:
                break
        return move, value


def bot_move(board, bot_piece):
    player_piece = other_piece(bot_piece)
    moves = avaiable_moves(board)

    for move in moves:
        board_copy = copy_board(board)
        set_piece(board_copy, move, bot_piece)
        if winning_move(board_copy, bot_piece):
            return move
    for move in moves:
        board_copy = copy_board(board)
        set_piece(board_copy, move, player_piece)
        if winning_move(board_copy, player_piece):
            return move
    return choice(moves) if moves else None


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
        board = get_board(game_id)
        for move in moves:
            send_update(game_id, move)
        if not moves:
            emit('update', {
                'turn': 1,
                'availableMoves': avaiable_moves(board)
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
    board = get_board(game_id)
    player_won = winning_move(board, move['piece'])
    if game['opponent'] == 'bot' and not player_won:
        bot_piece = other_piece(move['piece'])
        # move = bot_move(board, bot_piece)
        move, _ = minimax(board, 4, -math.inf, math.inf, True, bot_piece)
        move = {'piece': bot_piece, 'row': move[0], 'col': move[1]}
        add_move(game_id, move)
        send_update(game_id, move)


def send_update(game_id, move):
    board = get_board(game_id)
    emit('update', {
        'move': move,
        'turn': other_piece(move['piece']),
        'availableMoves': avaiable_moves(board),
        'winningMove': winning_move(board, move['piece'])
    }, room=game_id)
