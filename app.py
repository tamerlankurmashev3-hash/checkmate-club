import os
import secrets
import string
from threading import Lock

import chess
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
socketio = SocketIO(app, async_mode="threading")

games = {}
player_rooms = {}
games_lock = Lock()
ROOM_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@app.get("/")
def index():
    return render_template("chess.html")


def clean_name(value):
    name = " ".join(str(value or "Player").split())[:20]
    return name or "Player"


def fresh_room_code():
    while True:
        code = "".join(secrets.choice(ROOM_CHARS) for _ in range(6))
        if code not in games:
            return code


def game_state(room):
    game = games[room]
    board = game["board"]
    return {
        "room": room,
        "fen": board.fen(),
        "moves": game["moves"],
        "positions": game["positions"],
        "last_move": game["last_move"],
        "turn": "w" if board.turn else "b",
        "players": game["names"],
        "draw_offer": game["draw_offer"],
        "finished": game["finished"],
    }


def send_state(room):
    socketio.emit("game_state", game_state(room), to=room)


def finish_game(room, title, text):
    game = games[room]
    game["finished"] = True
    socketio.emit("game_over", {"title": title, "text": text}, to=room)


@socketio.on("create_game")
def create_game(data):
    name = clean_name((data or {}).get("name"))
    with games_lock:
        room = fresh_room_code()
        games[room] = {
            "board": chess.Board(),
            "moves": [],
            "positions": [],
            "last_move": None,
            "players": {"w": request.sid, "b": None},
            "names": {"w": name, "b": "Waiting for a friend"},
            "draw_offer": None,
            "finished": False,
        }
        games[room]["positions"] = [games[room]["board"].board_fen() + " w KQkq -"]
        player_rooms[request.sid] = (room, "w")
    join_room(room)
    emit("room_ready", {"room": room, "color": "w", "name": name})


@socketio.on("join_game")
def join_game(data):
    data = data or {}
    room = "".join(c for c in str(data.get("room", "")).upper() if c in ROOM_CHARS)[:6]
    name = clean_name(data.get("name"))
    with games_lock:
        game = games.get(room)
        if not game:
            emit("room_error", {"message": "That invite room does not exist. Ask your friend to create a new invite."})
            return
        if request.sid in player_rooms:
            emit("room_error", {"message": "You are already in a game room."})
            return
        color = "b" if game["players"]["b"] is None else None
        if color is None:
            emit("room_error", {"message": "This game already has two players."})
            return
        game["players"][color] = request.sid
        game["names"][color] = name
        player_rooms[request.sid] = (room, color)
        game["finished"] = False
    join_room(room)
    state = game_state(room)
    for side in ("w", "b"):
        socketio.emit("game_started", {**state, "color": side}, to=game["players"][side])


@socketio.on("make_move")
def make_move(data):
    data = data or {}
    identity = player_rooms.get(request.sid)
    if not identity:
        emit("room_error", {"message": "Join a game room before moving."})
        return
    room, color = identity
    game = games.get(room)
    if not game or game["finished"] or game["players"].get(color) != request.sid:
        return
    board = game["board"]
    if ("w" if board.turn else "b") != color:
        emit("room_error", {"message": "Wait for your turn."})
        return
    try:
        move = chess.Move.from_uci(str(data.get("uci", "")))
    except (ValueError, TypeError):
        emit("room_error", {"message": "That move could not be read."})
        return
    if move not in board.legal_moves:
        emit("room_error", {"message": "That is not a legal move."})
        return
    game["moves"].append(board.san(move))
    board.push(move)
    game["last_move"] = move.uci()
    game["positions"].append(board.board_fen() + (" w " if board.turn else " b ") + (board.castling_xfen() or "-") + " " + (chess.square_name(board.ep_square) if board.ep_square is not None else "-"))
    game["draw_offer"] = None
    send_state(room)
    if board.is_checkmate():
        finish_game(room, "Checkmate", f"{game['names'][color]} wins the game.")
    elif board.is_stalemate() or board.is_insufficient_material() or board.can_claim_fifty_moves() or board.can_claim_threefold_repetition():
        finish_game(room, "A draw", "The game ended in a draw.")


@socketio.on("offer_draw")
def offer_draw(_data=None):
    identity = player_rooms.get(request.sid)
    if not identity:
        return
    room, color = identity
    game = games.get(room)
    if not game or game["finished"]:
        return
    if game["draw_offer"] and game["draw_offer"] != color:
        finish_game(room, "Draw agreed", "Both players agreed to a draw.")
    elif game["draw_offer"] == color:
        emit("room_error", {"message": "Your draw offer is waiting for your opponent."})
    else:
        game["draw_offer"] = color
        socketio.emit("draw_offered", {"by": game["names"][color]}, to=room)


@socketio.on("resign")
def resign(_data=None):
    identity = player_rooms.get(request.sid)
    if not identity:
        return
    room, color = identity
    game = games.get(room)
    if game and not game["finished"]:
        winner = "Black" if color == "w" else "White"
        finish_game(room, f"{winner} wins by resignation", f"{game['names'][color]} resigned.")


@socketio.on("restart_game")
def restart_game(_data=None):
    identity = player_rooms.get(request.sid)
    if not identity:
        return
    room, _color = identity
    game = games.get(room)
    if not game or not all(game["players"].values()):
        return
    game.update(board=chess.Board(), moves=[], last_move=None, draw_offer=None, finished=False)
    game["positions"] = [game["board"].board_fen() + " w KQkq -"]
    send_state(room)


@socketio.on("disconnect")
def disconnect():
    identity = player_rooms.pop(request.sid, None)
    if not identity:
        return
    room, color = identity
    game = games.get(room)
    if not game:
        return
    game["players"][color] = None
    game["names"][color] = "Waiting for a friend"
    game["finished"] = True
    socketio.emit("opponent_left", {"color": color}, to=room)


if __name__ == "__main__":
    hosted = "PORT" in os.environ
    socketio.run(app, host="0.0.0.0" if hosted else "127.0.0.1", port=int(os.environ.get("PORT", os.environ.get("CHESS_PORT", "5003"))), debug=False, allow_unsafe_werkzeug=not hosted)
