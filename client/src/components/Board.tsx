import { DragEvent, memo } from "react";
import { BOARD_SIZE, CENTER } from "../lib/rules";
import { getPremium } from "../lib/premium";
import { Direction, PlacementDraft, BoardTile as BoardTileType } from "../types";

interface BoardProps {
  boardMap: Map<string, BoardTileType>;
  placements: PlacementDraft[];
  anchor: { row: number; col: number } | null;
  cursor: { row: number; col: number } | null;
  direction: Direction;
  onCellClick: (row: number, col: number) => void;
  onTileDrop?: (payload: {
    row: number;
    col: number;
    rackIndex: number;
    letter: string;
    isBlank: boolean;
  }) => void;
}

const TILE_MIME = "application/x-scrabble-tile";

const Board = ({
  boardMap,
  placements,
  anchor,
  cursor,
  direction,
  onCellClick,
  onTileDrop,
}: BoardProps) => {
  const placementMap = new Map<string, PlacementDraft>();
  placements.forEach((placement) => {
    placementMap.set(`${placement.row}:${placement.col}`, placement);
  });

  const renderCell = (row: number, col: number) => {
    const key = `${row}:${col}`;
    const premium = getPremium(row, col);
    const boardTile = boardMap.get(key);
    const placement = placementMap.get(key);
    const isAnchor = anchor && anchor.row === row && anchor.col === col;
    const isCursor = cursor && cursor.row === row && cursor.col === col;

    let letter = "";
    let tileClass = "tile";

    if (boardTile) {
      letter = boardTile.letter;
      tileClass += " tile--locked";
    }
    if (placement) {
      letter = placement.letter;
      tileClass += " tile--draft";
      if (placement.isBlank) {
        tileClass += " tile--blank";
      }
    }
    if (!boardTile && !placement && row === CENTER.row && col === CENTER.col) {
      tileClass += " tile--center";
    }
    if (isAnchor) {
      tileClass += " tile--anchor";
      tileClass += direction === "horizontal" ? " tile--anchor-horizontal" : " tile--anchor-vertical";
    }
    if (isCursor) {
      tileClass += " tile--cursor";
    }

    let premiumLabel = "";
    if (!boardTile && !placement && premium) {
      premiumLabel = premium;
    }

    const handleDragOver = (event: DragEvent<HTMLButtonElement>) => {
      if (!onTileDrop) {
        return;
      }
      if (boardTile || placement) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    };

    const handleDrop = (event: DragEvent<HTMLButtonElement>) => {
      if (!onTileDrop) {
        return;
      }
      if (boardTile || placement) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const raw = event.dataTransfer.getData(TILE_MIME);
      if (!raw) {
        return;
      }
      try {
        const data = JSON.parse(raw) as {
          rackIndex?: number;
          letter?: string;
          isBlank?: boolean;
        };
        if (
          typeof data?.rackIndex !== "number" ||
          typeof data?.letter !== "string" ||
          typeof data?.isBlank !== "boolean"
        ) {
          return;
        }
        onTileDrop({
          row,
          col,
          rackIndex: data.rackIndex,
          letter: data.letter,
          isBlank: data.isBlank,
        });
      } catch (error) {
        console.warn("Could not parse dropped tile", error);
      }
    };

    return (
      <button
        key={key}
        type="button"
        className={`board-cell premium-${premium ?? "none"}`.trim()}
        onClick={() => onCellClick(row, col)}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <span className={tileClass}>{letter || premiumLabel}</span>
      </button>
    );
  };

  const rows = [];
  for (let row = 0; row < BOARD_SIZE; row += 1) {
    const cols = [];
    for (let col = 0; col < BOARD_SIZE; col += 1) {
      cols.push(renderCell(row, col));
    }
    rows.push(
      <div key={row} className="board-row">
        {cols}
      </div>
    );
  }

  return <div className="board">{rows}</div>;
};

export default memo(Board);
