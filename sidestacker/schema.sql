DROP TABLE IF EXISTS games;
DROP TABLE IF EXISTS moves;

CREATE TABLE games (
    id TEXT NOT NULL,
    player1_id TEXT NOT NULL,
    player2_id TEXT NULL,
    opponent TEXT NOT NULL
);

CREATE TABLE moves (
    game_id TEXT NOT NULL,
    piece INTEGER NOT NULL,
    row INTEGER NOT NULL,
    col INTEGER NOT NULL
);
