# Scrabble Duel

A two-player Scrabble experience built with FastAPI and React. The FastAPI server is the single source of truth for matchmaking, tile draws, scoring, and dictionary validation. The React client provides the interactive board, rack management, and turn workflow defined in Stage 1 of the challenge.

## Project Layout

```
.
├── README.md
├── challenge.txt              # Original challenge brief
├── CSW24.txt                  # Dictionary (Collins Scrabble Words 2024)
├── server/                    # FastAPI application and game engine
│   └── app/
│       ├── api/               # HTTP endpoints and shared managers
│       ├── core/              # Rules, constants, dictionary loader
│       ├── models/            # In-memory game entities and logic
│       ├── services/          # Lobby, connection, and game orchestration
│       └── main.py            # FastAPI application wiring & WebSockets
└── client/                    # React (Vite + TypeScript) single-page app
    └── src/
        ├── components/        # Board, rack, dialogs, warnings
        ├── lib/               # Shared board rules/premiums
        ├── types.ts           # Client-side DTOs
        ├── App.tsx            # Game experience glue
        └── styles.css         # UI styling
```

## Prerequisites

- Python 3.11+
- Node.js 18+

## Backend Setup

```bash
cd server
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Key backend features:

- FastAPI + WebSockets for lobby matchmaking and live state pushes
- In-memory game engine enforcing Scrabble rules, premium squares, and CSW24 dictionary validation
- Support for concurrent games; each game guarded by its own asyncio lock
- Authoritative tile bag and rack management (randomized draws, blank tracking)

## Frontend Setup

```bash
cd client
npm install
npm run dev
```

The Vite dev server proxies API (`/api/*`) and WebSocket (`/ws/*`) traffic to the FastAPI instance on port 8000.

## Gameplay Flow

1. Open the frontend, enter a display name, and choose between playing the bot or waiting for another human.
2. When you pick multiplayer, a second player joining the lobby triggers match creation. Bot mode spins up an AI opponent instantly.
3. On your turn:
   - Click an empty board square to choose a starting cell. Click it again (before typing) to toggle between horizontal/vertical.
   - Type letters on your keyboard to lay tiles. Occupied squares in the path are skipped automatically.
   - Hold `Shift` while typing a letter to force usage of a blank tile.
   - `Backspace` removes the most recent tile, `Esc` clears the whole draft.
   - `Enter` submits the word; if no tiles are placed a confirmation dialog prompts you to pass.
   - Press `X` (or use the button) with no tiles on the board to open the exchange dialog.
4. Manage your rack:
   - Drag tiles to reorder them for planning.
   - Use the shuffle button for a random arrangement.
5. The sidebar shows scores, bag count, and move history. All warnings for invalid actions (wrong turn, missing tiles, off-board words, missing start) appear inline.

## Game Clock

- Each player receives 10 minutes (600 seconds) per game. The FastAPI server owns the clock and decrements it once per second.
- When a game starts, a background task in the server keeps the active player's clock in sync and pushes WebSocket updates. Clients never run their own authoritative timers.
- If a player’s time reaches zero, the server immediately ends the game, marks the opponent as winner by timeout, and the UI reflects the result.
- The React client shows a synchronized countdown for both players using the server-provided `clocks` snapshot and `serverTime` timestamp.

## Bot Mode

- Selecting “Challenge Bot” in the lobby spins up a lightweight AI opponent that draws from the same tile bag and dictionary as humans.
- The bot searches for quick legal moves by simulating candidate placements against the game engine; if no move is available it will pass.
- A dedicated task keeps the bot responsive and ensures it plays within the 30-second budget per turn.

## Verification

- `python -m compileall server` ✅
- Manual walkthrough of client behaviours via key handlers in `App.tsx`

## Next Steps

- Add persistence (Redis/Postgres) to support server restarts.
- Extend error handling with granular codes for richer client UX.
- Stage 4: evolve the bot with stronger heuristics and multi-turn planning.
