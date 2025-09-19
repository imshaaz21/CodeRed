import { DragEvent } from "react";
import { RackTile } from "../types";

interface RackProps {
  rack: RackTile[];
  order: number[];
  placements: number[];
  onReorder: (order: number[]) => void;
  onShuffle: () => void;
}

const TILE_MIME = "application/x-scrabble-tile";
const RACK_POSITION_MIME = "application/x-scrabble-rack-pos";

const Rack = ({ rack, order, placements, onReorder, onShuffle }: RackProps) => {
  const handleDragStart = (
    event: DragEvent<HTMLDivElement>,
    position: number,
    rackIndex: number,
    tile: RackTile
  ) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(RACK_POSITION_MIME, position.toString());
    event.dataTransfer.setData(
      TILE_MIME,
      JSON.stringify({ rackIndex, letter: tile.letter, isBlank: tile.isBlank })
    );
    event.dataTransfer.setData("text/plain", tile.letter);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>, index: number) => {
    event.preventDefault();
    const data = event.dataTransfer.getData(RACK_POSITION_MIME);
    if (!data) {
      return;
    }
    const sourceIndex = Number(data);
    if (Number.isNaN(sourceIndex)) {
      return;
    }
    if (sourceIndex === index) {
      return;
    }
    const updated = [...order];
    const [removed] = updated.splice(sourceIndex, 1);
    updated.splice(index, 0, removed);
    onReorder(updated);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  return (
    <div className="rack">
      <div className="rack-tiles">
        {order.map((rackIndex, position) => {
          const tile = rack[rackIndex];
          if (!tile) {
            return null;
          }
          const isUsed = placements.includes(rackIndex);
          return (
            <div
              key={`${rackIndex}-${tile.letter}-${position}`}
              className={`rack-tile${isUsed ? " rack-tile--used" : ""}`}
              draggable={!isUsed}
              onDragStart={(event) => handleDragStart(event, position, rackIndex, tile)}
              onDrop={(event) => handleDrop(event, position)}
              onDragOver={handleDragOver}
            >
              <span className="rack-letter">{tile.letter}</span>
            </div>
          );
        })}
      </div>
      <button type="button" className="rack-shuffle" onClick={onShuffle}>
        Shuffle Rack
      </button>
    </div>
  );
};

export default Rack;
