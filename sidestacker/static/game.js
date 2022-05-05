;(function () {
    'use strict'

    function onJoin(data) {
        if (document.querySelector('.opponent').getAttribute('hidden') === '') {
            document.querySelector('.opponent').toggleAttribute('hidden')
            document.querySelector('.waiting').toggleAttribute('hidden')
        }
    }

    function toggleDisabled(turn, availableMoves) {
        document.querySelectorAll('.space').forEach((button) => {
            const row = parseInt(button.dataset.row)
            const col = parseInt(button.dataset.col)
            let hasPiece = button.classList.contains('piece1') || button.classList.contains('piece2')
            if (!hasPiece) {
                if (turn == PIECE && availableMoves[row] && availableMoves[row].includes(col)) {
                    button.removeAttribute('disabled')
                } else {
                    button.setAttribute('disabled', '')
                }
            }
        })
    }

    function otherPiece(piece) {
        return piece == 1 ? 2 : 1
    }

    function onUpdate(data) {
        if (data.move) {
            const button = document.querySelector(`button[data-row="${data.move.row}"][data-col="${data.move.col}"]`)
            button.classList.add('piece' + data.move.piece)
            button.setAttribute('disabled', '')
        }

        if (data.winningMove) {
            const message = data.move.piece == PIECE ? `Player ${data.move.piece} won` : `Player ${otherPiece(data.move.piece)} lost`
            toggleDisabled(data.move.piece, [])
            document.querySelector('#status').innerHTML = message
        } else {
            document.querySelector('#player' + otherPiece(data.turn)).classList.remove('next-turn')
            document.querySelector('#player' + data.turn).classList.add('next-turn')
            toggleDisabled(data.turn, data.availableMoves)
            document.querySelector('#status').innerHTML = data.turn == PIECE ? 'Your turn' : 'Opponent\'s turn'
        }
    }

    function onMove(event) {
        const button = event.target
        const row = parseInt(button.dataset.row)
        const col = parseInt(button.dataset.col)
        socket.emit('move', {row, col})
    }

    function onEnd(data) {
        document.forms[0].submit()
    }

    const socket = io()

    window.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.space').forEach(button => button.addEventListener('click', onMove))
        socket.on('join', onJoin)
        socket.on('update', onUpdate)
        socket.on('end', onEnd)
    })
})()
