import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import Board from "./components/Board";
import ConfirmModal from "./components/ConfirmModal";
import ExchangeModal from "./components/ExchangeModal";
import JoinForm from "./components/JoinForm";
import Rack from "./components/Rack";
import WarningBanner from "./components/WarningBanner";
import { BOARD_SIZE } from "./lib/rules";
import { BoardTile, Direction, GameStatePayload, PlacementDraft } from "./types";

const boardKey = (row: number, col: number) => `${row}:${col}`;

type Phase = "join" | "waiting" | "active";

type WarningKind =
  | "INVALID_TURN"
  | "INVALID_TILE"
  | "WORD_OFF_BOARD"
  | "NO_START"
  | "SQUARE_OCCUPIED"
  | "CLEAR_BEFORE_SWITCH"
  | "NEED_SELECTION"
  | "SERVER_ERROR";

const WARNING_MESSAGE: Record<WarningKind, string> = {
  INVALID_TURN: "It is not your turn.",
  INVALID_TILE: "That tile is not available in your rack.",
  WORD_OFF_BOARD: "That word would go off the board.",
  NO_START: "Click an empty square to choose a starting point first.",
  SQUARE_OCCUPIED: "Pick an empty square to start your word.",
  CLEAR_BEFORE_SWITCH: "Finish or clear your current move before changing direction.",
  NEED_SELECTION: "Select at least one tile to exchange.",
  SERVER_ERROR: "The server rejected that action. Please adjust and try again.",
};

interface CursorState {
  row: number;
  col: number;
}

const isLetterKey = (key: string) => /^[a-zA-Z]$/.test(key);

const buildBoardMap = (board: BoardTile[]) => {
  const map = new Map<string, BoardTile>();
  board.forEach((tile) => map.set(boardKey(tile.row, tile.col), tile));
  return map;
};

const computeNextCursor = (
  from: CursorState,
  direction: Direction,
  boardMap: Map<string, BoardTile>,
  placementMap: Map<string, PlacementDraft>
): CursorState | null => {
  let { row, col } = from;
  while (true) {
    if (direction === "horizontal") {
      col += 1;
    } else {
      row += 1;
    }
    if (row < 0 || col < 0 || row >= BOARD_SIZE || col >= BOARD_SIZE) {
      return null;
    }
    const key = boardKey(row, col);
    if (!boardMap.has(key) && !placementMap.has(key)) {
      return { row, col };
    }
  }
};

interface DroppedTilePayload {
  row: number;
  col: number;
  rackIndex: number;
  letter: string;
  isBlank: boolean;
}

const App = () => {
  const [phase, setPhase] = useState<Phase>("join");
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [gameId, setGameId] = useState<string | null>(null);
  const [gameState, setGameState] = useState<GameStatePayload | null>(null);
  const [placements, setPlacements] = useState<PlacementDraft[]>([]);
  const [anchor, setAnchor] = useState<CursorState | null>(null);
  const [direction, setDirection] = useState<Direction>("horizontal");
  const [cursor, setCursor] = useState<CursorState | null>(null);
  const [rackOrder, setRackOrder] = useState<number[]>([]);
  const [warning, setWarning] = useState<string | null>(null);
  const warningTimer = useRef<number | null>(null);
  const [exchangeOpen, setExchangeOpen] = useState(false);
  const [exchangeSelection, setExchangeSelection] = useState<number[]>([]);
  const [busyAction, setBusyAction] = useState(false);
  const [passConfirmOpen, setPassConfirmOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const websocketRef = useRef<WebSocket | null>(null);

  const boardMap = useMemo(() => buildBoardMap(gameState?.board ?? []), [gameState]);
  const placementMap = useMemo(() => {
    const map = new Map<string, PlacementDraft>();
    placements.forEach((placement) => map.set(boardKey(placement.row, placement.col), placement));
    return map;
  }, [placements]);

  const showWarning = useCallback(
    (kind: WarningKind, customMessage?: string) => {
      const message = customMessage ?? WARNING_MESSAGE[kind];
      setWarning(message);
      if (warningTimer.current) {
        window.clearTimeout(warningTimer.current);
      }
      warningTimer.current = window.setTimeout(() => {
        setWarning(null);
      }, 2600);
    },
    []
  );

  const isMyTurn = useMemo(() => {
    if (!gameState || !playerId) {
      return false;
    }
    return gameState.turn === playerId && gameState.status === "active";
  }, [gameState, playerId]);

  const usedRackIndices = useMemo(() => placements.map((placement) => placement.rackIndex), [placements]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setNow(Date.now());
    }, 250);
    return () => window.clearInterval(interval);
  }, []);

  const effectiveClocks = useMemo(() => {
    if (!gameState) {
      return {} as Record<string, number>;
    }
    const snapshot: Record<string, number> = { ...gameState.clocks };
    const serverTimestamp = Date.parse(gameState.serverTime);
    if (!Number.isNaN(serverTimestamp) && gameState.status === "active") {
      const deltaSeconds = (now - serverTimestamp) / 1000;
      if (deltaSeconds > 0) {
        const activePlayer = gameState.turn;
        const baseline = snapshot[activePlayer] ?? 0;
        snapshot[activePlayer] = Math.max(0, baseline - deltaSeconds);
      }
    }
    return snapshot;
  }, [gameState, now]);

  useEffect(() => {
    if (!gameState) {
      return;
    }
    setRackOrder((prev) => {
      if (prev.length === gameState.rack.length) {
        return prev;
      }
      return Array.from({ length: gameState.rack.length }, (_, index) => index);
    });

    setPlacements((prev) =>
      prev.filter((placement) => !boardMap.has(boardKey(placement.row, placement.col)))
    );
  }, [gameState, boardMap]);

  const joinLobby = useCallback(
    async (displayName: string) => {
      setPhase("waiting");
      const response = await axios.post<{ playerId: string }>("/api/lobby/join", {
        displayName,
      });
      setPlayerId(response.data.playerId);
    },
    []
  );

  useEffect(() => {
    if (!playerId) {
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${protocol}://${window.location.host}/ws/lobby/${playerId}`;
    const ws = new WebSocket(wsUrl);
    websocketRef.current = ws;

    ws.onopen = () => {
      setPhase((current) => (current === "join" ? "waiting" : current));
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "match_found") {
          setGameId(message.gameId);
          setPhase("active");
        }
        if (message.type === "state") {
          setGameState(message.payload);
          setPhase("active");
        }
      } catch (error) {
        console.error("Failed to parse message", error);
      }
    };

    ws.onclose = () => {
      websocketRef.current = null;
    };

    return () => {
      ws.close();
      websocketRef.current = null;
    };
  }, [playerId]);

  const resetCurrentMove = useCallback(() => {
    setPlacements([]);
    setExchangeSelection([]);
    setCursor(anchor);
  }, [anchor]);

  const findRackIndex = useCallback(
    (letter: string, useBlank: boolean) => {
      if (!gameState) {
        return null;
      }
      const available = new Set(rackOrder);
      usedRackIndices.forEach((index) => available.delete(index));

      if (useBlank) {
        for (const rackIndex of available) {
          if (gameState.rack[rackIndex]?.isBlank) {
            return rackIndex;
          }
        }
        return null;
      }

      for (const rackIndex of available) {
        const tile = gameState.rack[rackIndex];
        if (tile && !tile.isBlank && tile.letter === letter) {
          return rackIndex;
        }
      }
      return null;
    },
    [gameState, rackOrder, usedRackIndices]
  );

  const hasBlankAvailable = useCallback(() => {
    if (!gameState) {
      return false;
    }
    const available = new Set(rackOrder);
    usedRackIndices.forEach((index) => available.delete(index));
    for (const rackIndex of available) {
      if (gameState.rack[rackIndex]?.isBlank) {
        return true;
      }
    }
    return false;
  }, [gameState, rackOrder, usedRackIndices]);

  const placeLetter = useCallback(
    (letter: string, useBlank: boolean) => {
      if (!isMyTurn) {
        showWarning("INVALID_TURN");
        return;
      }
      if (!anchor) {
        showWarning("NO_START");
        return;
      }
      if (!cursor) {
        showWarning("WORD_OFF_BOARD");
        return;
      }
      let target = cursor;
      let targetKey = boardKey(target.row, target.col);
      let probe = cursor;
      while (boardMap.has(targetKey) || placementMap.has(targetKey)) {
        const next = computeNextCursor(probe, direction, boardMap, placementMap);
        if (!next) {
          showWarning("WORD_OFF_BOARD");
          return;
        }
        target = next;
        targetKey = boardKey(target.row, target.col);
        probe = next;
      }

      const rackIndex = findRackIndex(letter, useBlank);
      if (rackIndex === null) {
        if (!useBlank && hasBlankAvailable()) {
          showWarning("INVALID_TILE", "Press Shift + letter to use a blank tile.");
        } else {
          showWarning("INVALID_TILE");
        }
        return;
      }

      const placement: PlacementDraft = {
        row: target.row,
        col: target.col,
        letter,
        isBlank: useBlank,
        rackIndex,
      };
      setPlacements((prev) => [...prev, placement]);

      const nextCursor = computeNextCursor(
        target,
        direction,
        boardMap,
        new Map(placementMap).set(targetKey, placement)
      );
      if (nextCursor) {
        setCursor(nextCursor);
      } else {
        setCursor(null);
      }
    },
    [
      anchor,
      boardMap,
      cursor,
      direction,
      findRackIndex,
      hasBlankAvailable,
      isMyTurn,
      placementMap,
      showWarning,
    ]
  );

  const handleBoardClick = useCallback(
    (row: number, col: number) => {
      if (!isMyTurn) {
        showWarning("INVALID_TURN");
        return;
      }
      const key = boardKey(row, col);
      if (boardMap.has(key)) {
        showWarning("SQUARE_OCCUPIED");
        return;
      }
      const sameAnchor = anchor && anchor.row === row && anchor.col === col;
      if (placements.length > 0) {
        showWarning("CLEAR_BEFORE_SWITCH");
        return;
      }
      if (sameAnchor) {
        setDirection(direction === "horizontal" ? "vertical" : "horizontal");
        setCursor({ row, col });
        return;
      }
      setAnchor({ row, col });
      setCursor({ row, col });
      setDirection("horizontal");
      setPlacements([]);
    },
    [anchor, boardMap, direction, isMyTurn, placements, showWarning]
  );

  const handleSubmitMove = useCallback(async () => {
    if (!playerId || !gameId || placements.length === 0) {
      return;
    }
    if (!isMyTurn) {
      showWarning("INVALID_TURN");
      return;
    }
    setBusyAction(true);
    try {
      const payload = placements.map((placement) => ({
        row: placement.row,
        col: placement.col,
        letter: placement.letter,
        isBlank: placement.isBlank,
      }));
      await axios.post(`/api/game/${gameId}/move`, {
        playerId,
        placements: payload,
      });
      setPlacements([]);
      setCursor(anchor);
    } catch (error) {
      console.error(error);
      showWarning("SERVER_ERROR");
    } finally {
      setBusyAction(false);
    }
  }, [anchor, gameId, isMyTurn, placements, playerId, showWarning]);

  const handlePassTurn = useCallback(async () => {
    if (!playerId || !gameId) {
      return;
    }
    if (!isMyTurn) {
      showWarning("INVALID_TURN");
      return;
    }
    setBusyAction(true);
    try {
      await axios.post(`/api/game/${gameId}/pass`, { playerId });
      setPlacements([]);
      setCursor(anchor);
    } catch (error) {
      console.error(error);
      showWarning("SERVER_ERROR");
    } finally {
      setBusyAction(false);
    }
  }, [anchor, gameId, isMyTurn, playerId, showWarning]);

  const confirmExchange = useCallback(async () => {
    if (!playerId || !gameId) {
      return;
    }
    if (!isMyTurn) {
      showWarning("INVALID_TURN");
      return;
    }
    if (exchangeSelection.length === 0) {
      showWarning("NEED_SELECTION");
      return;
    }
    if (placements.length > 0) {
      showWarning("CLEAR_BEFORE_SWITCH", "Clear placed tiles before exchanging.");
      return;
    }
    setBusyAction(true);
    try {
      const letters = exchangeSelection.map((rackIndex) => {
        const tile = gameState?.rack[rackIndex];
        return tile?.isBlank ? "?" : tile?.letter ?? "";
      });
      await axios.post(`/api/game/${gameId}/exchange`, {
        playerId,
        letters,
      });
      setExchangeSelection([]);
      setExchangeOpen(false);
    } catch (error) {
      console.error(error);
      showWarning("SERVER_ERROR");
    } finally {
      setBusyAction(false);
    }
  }, [exchangeSelection, gameId, gameState?.rack, isMyTurn, placements.length, playerId, showWarning]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (phase !== "active" || !gameState || !playerId) {
        return;
      }
      const target = event.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }
      if (exchangeOpen) {
        return;
      }

      if (event.key === "Enter") {
        if (placements.length === 0) {
          setPassConfirmOpen(true);
        } else {
          handleSubmitMove();
        }
        event.preventDefault();
        return;
      }

      if (event.key === "Escape") {
        setPlacements([]);
        setCursor(anchor);
        event.preventDefault();
        return;
      }

      if (event.key === "Backspace") {
        if (placements.length > 0) {
          setPlacements((prev) => {
            const updated = [...prev];
            const removed = updated.pop();
            if (removed) {
              setCursor({ row: removed.row, col: removed.col });
            }
            return updated;
          });
          event.preventDefault();
        }
        return;
      }

      if ((event.key === "x" || event.key === "X") && placements.length === 0) {
        setExchangeOpen(true);
        event.preventDefault();
        return;
      }

      if (isLetterKey(event.key)) {
        const letter = event.key.toUpperCase();
        const useBlank = event.shiftKey && hasBlankAvailable();
        placeLetter(letter, useBlank);
        event.preventDefault();
      }
    },
    [
      anchor,
      exchangeOpen,
      handlePassTurn,
      handleSubmitMove,
      hasBlankAvailable,
      phase,
      placements.length,
      placeLetter,
      gameState,
      playerId,
    ]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleKeyDown]);

  const shuffleRack = useCallback(() => {
    setRackOrder((prev) => {
      const shuffled = [...prev];
      for (let i = shuffled.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
      }
      return shuffled;
    });
  }, []);

  const toggleExchangeSelection = useCallback(
    (rackIndex: number) => {
      setExchangeSelection((prev) => {
        if (prev.includes(rackIndex)) {
          return prev.filter((index) => index !== rackIndex);
        }
        return [...prev, rackIndex];
      });
    },
    []
  );

  const formatClock = useCallback((seconds?: number) => {
    const safe = Math.max(0, Math.ceil(seconds ?? 0));
    const minutes = Math.floor(safe / 60)
      .toString()
      .padStart(2, "0");
    const secs = (safe % 60).toString().padStart(2, "0");
    return `${minutes}:${secs}`;
  }, []);

  const resultMessage = useMemo(() => {
    if (!gameState || gameState.status !== "completed" || !gameState.result) {
      return null;
    }
    if (gameState.result.reason === "timeout") {
      if (playerId && gameState.result.loser === playerId) {
        return "You ran out of time.";
      }
      return `${gameState.opponent.displayName} ran out of time.`;
    }
    return null;
  }, [gameState, playerId]);

  const myClock = playerId ? effectiveClocks[playerId] : undefined;
  const opponentClock = gameState ? effectiveClocks[gameState.opponent.playerId] : undefined;
  const opponentTurn = gameState ? gameState.turn === gameState.opponent.playerId : false;
  const myClockClass = isMyTurn && gameState?.status === "active" ? "clock-value clock-value--active" : "clock-value";
  const opponentClockClass = opponentTurn && gameState?.status === "active" ? "clock-value clock-value--active" : "clock-value";

  const handleTileDrop = useCallback(
    ({ row, col, rackIndex, letter, isBlank }: DroppedTilePayload) => {
      if (!isMyTurn) {
        showWarning("INVALID_TURN");
        return;
      }
      if (!gameState) {
        return;
      }
      const key = boardKey(row, col);
      if (boardMap.has(key) || placementMap.has(key)) {
        showWarning("SQUARE_OCCUPIED");
        return;
      }
      if (!gameState.rack[rackIndex]) {
        showWarning("INVALID_TILE");
        return;
      }
      if (usedRackIndices.includes(rackIndex)) {
        showWarning("INVALID_TILE", "That tile is already placed on the board.");
        return;
      }

      let resolvedLetter = letter.toUpperCase();
      let resolvedBlank = isBlank;
      if (resolvedBlank && !/^[A-Z]$/.test(resolvedLetter)) {
        const assignment = window.prompt("Choose a letter for the blank tile (A-Z):", "");
        if (!assignment) {
          return;
        }
        const normalized = assignment.trim().toUpperCase();
        if (!/^[A-Z]$/.test(normalized)) {
          showWarning("INVALID_TILE", "Blank tiles must be assigned a letter A-Z.");
          return;
        }
        resolvedLetter = normalized;
      }

      let candidateAnchor = anchor;
      let candidateDirection: Direction = direction;

      if (!candidateAnchor || (placements.length === 0 && (candidateAnchor.row !== row || candidateAnchor.col !== col))) {
        candidateAnchor = { row, col };
        candidateDirection = "horizontal";
      }

      if (candidateAnchor) {
        const sameRow = candidateAnchor.row === row;
        const sameCol = candidateAnchor.col === col;

        if (placements.length === 1) {
          if (sameRow && !sameCol) {
            candidateDirection = "horizontal";
          } else if (sameCol && !sameRow) {
            candidateDirection = "vertical";
          } else if (!sameRow || !sameCol) {
            showWarning("CLEAR_BEFORE_SWITCH", "Keep the word in a single row or column.");
            return;
          }
        } else if (placements.length > 1) {
          if (candidateDirection === "horizontal" && !sameRow) {
            showWarning("CLEAR_BEFORE_SWITCH", "Current placements are horizontal.");
            return;
          }
          if (candidateDirection === "vertical" && !sameCol) {
            showWarning("CLEAR_BEFORE_SWITCH", "Current placements are vertical.");
            return;
          }
        }
      }

      const newPlacement: PlacementDraft = {
        row,
        col,
        letter: resolvedLetter,
        isBlank: resolvedBlank,
        rackIndex,
      };

      const updatedPlacementsMap = new Map(placementMap);
      updatedPlacementsMap.set(key, newPlacement);

      setPlacements((prev) => [...prev, newPlacement]);

      if (!anchor || (placements.length === 0 && (anchor.row !== row || anchor.col !== col))) {
        setAnchor({ row, col });
      }
      if (!anchor || direction !== candidateDirection) {
        setDirection(candidateDirection);
      }

      const nextCursor = computeNextCursor({ row, col }, candidateDirection, boardMap, updatedPlacementsMap);
      setCursor(nextCursor);

      console.info(`Tile dropped: ${resolvedLetter} (rack index ${rackIndex}) -> (${row}, ${col})`);
    },
    [
      anchor,
      boardMap,
      direction,
      gameState,
      isMyTurn,
      placementMap,
      placements,
      showWarning,
      usedRackIndices,
    ]
  );

  const myScore = playerId ? gameState?.scores[playerId] ?? 0 : 0;
  const opponentScore = playerId && gameState ? gameState.scores[gameState.opponent.playerId] ?? 0 : 0;

  return (
    <div className="app">
      <WarningBanner message={warning} />
      {phase === "join" && <JoinForm onJoin={joinLobby} />}
      {phase !== "join" && !gameState && (
        <div className="waiting">
          <h2>Waiting for an opponent…</h2>
          <p>Leave this tab open. You will be matched automatically once another player arrives.</p>
        </div>
      )}
      {phase === "active" && gameState && (
        <div className="game-layout">
          <div className="sidebar">
            <section className="scorecard">
              <h2>Scores</h2>
              <p>
                You: <strong>{myScore}</strong>
              </p>
              <p className="clock-row">
                Your clock: <span className={myClockClass}>{formatClock(myClock)}</span>
              </p>
              <p>
                {gameState.opponent.displayName}: <strong>{opponentScore}</strong>
              </p>
              <p className="clock-row">
                {gameState.opponent.displayName}'s clock: <span className={opponentClockClass}>{formatClock(opponentClock)}</span>
              </p>
              <p>Bag tiles: {gameState.bagCount}</p>
              <p>Turn: {gameState.turnNumber}</p>
              <p className={isMyTurn ? "turn-indicator turn-indicator--active" : "turn-indicator"}>
                {isMyTurn ? "Your turn" : `${gameState.opponent.displayName}'s turn`}
              </p>
              {gameState.status === "completed" && (
                <p className="game-complete">
                  Game over{resultMessage ? ` — ${resultMessage}` : ""}
                </p>
              )}
            </section>
            <section className="history">
              <h3>Moves</h3>
              <ul>
                {gameState.moveHistory.map((move) => (
                  <li key={`${move.turn}-${move.playerId}`}>
                    <span>{move.type.toUpperCase()}</span>
                    {move.words.length > 0 && <span> {move.words.join(", ")}</span>}
                    <span> (+{move.score})</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
          <div className="stage">
            <Board
              boardMap={boardMap}
              placements={placements}
              anchor={anchor}
              cursor={cursor}
              direction={direction}
              onCellClick={handleBoardClick}
              onTileDrop={handleTileDrop}
            />
            <div className="controls">
              <Rack
                rack={gameState.rack}
                order={rackOrder}
                placements={usedRackIndices}
                onReorder={setRackOrder}
                onShuffle={shuffleRack}
              />
              <div className="control-buttons">
                <button
                  type="button"
                  onClick={handleSubmitMove}
                  disabled={!isMyTurn || placements.length === 0 || busyAction}
                >
                  Submit Word (Enter)
                </button>
                <button
                  type="button"
                  onClick={() => setPassConfirmOpen(true)}
                  disabled={!isMyTurn || busyAction}
                >
                  Pass Turn
                </button>
                <button
                  type="button"
                  onClick={() => setExchangeOpen(true)}
                  disabled={!isMyTurn || busyAction}
                >
                  Exchange Tiles (X)
                </button>
                <button type="button" onClick={resetCurrentMove}>
                  Clear Placement (Esc)
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      <ExchangeModal
        open={exchangeOpen}
        rack={gameState?.rack ?? []}
        order={rackOrder}
        used={usedRackIndices}
        selected={exchangeSelection}
        onToggle={toggleExchangeSelection}
        onClose={() => setExchangeOpen(false)}
        onConfirm={confirmExchange}
        busy={busyAction}
      />
      <ConfirmModal
        open={passConfirmOpen}
        title="Pass Turn"
        message="Are you sure you want to pass without playing any tiles?"
        confirmLabel="Pass"
        onCancel={() => setPassConfirmOpen(false)}
        onConfirm={async () => {
          setPassConfirmOpen(false);
          await handlePassTurn();
        }}
        busy={busyAction}
      />
    </div>
  );
};

export default App;
