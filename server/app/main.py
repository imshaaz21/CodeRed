from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import game_manager, lobby_manager, router, connections

app = FastAPI(title="Scrabble Duel API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.websocket("/ws/lobby/{player_id}")
async def lobby_socket(websocket: WebSocket, player_id: str):
    await connections.connect(player_id, websocket)
    await lobby_manager.mark_connected(player_id)

    game = await game_manager.get_game_for_player(player_id)
    if game:
        await connections.send(player_id, {"type": "state", "payload": game.to_player_view(player_id)})

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await lobby_manager.leave(player_id)
