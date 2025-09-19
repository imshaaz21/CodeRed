export interface BoardTile {
  row: number;
  col: number;
  letter: string;
  isBlank: boolean;
  placedBy: string;
}

export interface RackTile {
  letter: string;
  isBlank: boolean;
}

export interface MoveSummary {
  turn: number;
  playerId: string;
  type: string;
  score: number;
  words: string[];
}

export interface GameResult {
  winner: string;
  loser: string;
  reason: string;
}

export type LobbyMode = "multi" | "bot" | "bot-advanced";

export interface GameStatePayload {
  gameId: string;
  status: "active" | "completed";
  turn: string;
  turnNumber: number;
  scores: Record<string, number>;
  rack: RackTile[];
  board: BoardTile[];
  bagCount: number;
  moveHistory: MoveSummary[];
  opponent: {
    playerId: string;
    displayName: string;
    rackCount: number;
  };
  you: {
    playerId: string;
    displayName: string;
  };
  clocks: Record<string, number>;
  serverTime: string;
  result: GameResult | null;
}

export type Direction = "horizontal" | "vertical";

export interface PlacementDraft {
  row: number;
  col: number;
  letter: string;
  isBlank: boolean;
  rackIndex: number;
}
