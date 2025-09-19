import { RackTile } from "../types";

interface ExchangeModalProps {
  open: boolean;
  rack: RackTile[];
  order: number[];
  used: number[];
  selected: number[];
  onToggle: (rackIndex: number) => void;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  busy?: boolean;
}

const ExchangeModal = ({
  open,
  rack,
  order,
  used,
  selected,
  onToggle,
  onClose,
  onConfirm,
  busy = false,
}: ExchangeModalProps) => {
  if (!open) {
    return null;
  }
  const usedSet = new Set(used);
  const selectedSet = new Set(selected);

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Exchange Tiles</h2>
        <p>Select tiles to exchange. This will pass your turn.</p>
        <div className="modal-rack">
          {order.map((rackIndex) => {
            const tile = rack[rackIndex];
            if (!tile) {
              return null;
            }
            const disabled = usedSet.has(rackIndex);
            const isSelected = selectedSet.has(rackIndex);
            return (
              <button
                key={`exchange-${rackIndex}`}
                type="button"
                className={`modal-tile${disabled ? " modal-tile--disabled" : ""}${isSelected ? " modal-tile--selected" : ""}`}
                disabled={disabled}
                onClick={() => onToggle(rackIndex)}
              >
                {tile.letter}
              </button>
            );
          })}
        </div>
        <div className="modal-actions">
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" onClick={onConfirm} disabled={busy || selected.length === 0}>
            {busy ? "Exchanging…" : "Exchange"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ExchangeModal;
