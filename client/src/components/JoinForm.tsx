import { FormEvent, useState } from "react";
import { LobbyMode } from "../types";

interface JoinFormProps {
  onJoin: (displayName: string, mode: LobbyMode) => Promise<void>;
  busy?: boolean;
}

const JoinForm = ({ onJoin, busy = false }: JoinFormProps) => {
  const [name, setName] = useState("");
  const [mode, setMode] = useState<LobbyMode>("multi");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await onJoin(name.trim(), mode);
  };

  return (
    <form className="join-form" onSubmit={handleSubmit}>
      <h1>Scrabble Duel</h1>
      <label>
        Display name
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value.slice(0, 20))}
          placeholder="Enter your name"
          maxLength={20}
        />
      </label>
      <div className="mode-selector">
        <span>Choose mode:</span>
        <label>
          <input
            type="radio"
            name="mode"
            value="multi"
            checked={mode === "multi"}
            onChange={() => setMode("multi")}
            disabled={busy}
          />
          Play Online
        </label>
        <label>
          <input
            type="radio"
            name="mode"
            value="bot"
            checked={mode === "bot"}
            onChange={() => setMode("bot")}
            disabled={busy}
          />
          Challenge Bot
        </label>
        <label>
          <input
            type="radio"
            name="mode"
            value="bot-advanced"
            checked={mode === "bot-advanced"}
            onChange={() => setMode("bot-advanced")}
            disabled={busy}
          />
          Advanced Bot
        </label>
      </div>
      <button type="submit" disabled={busy}>
        {busy ? "Joining…" : "Join Lobby"}
      </button>
      <p className="hint">
        {mode === "bot"
          ? "The bot will join immediately after you connect."
          : mode === "bot-advanced"
          ? "The advanced bot will take a short moment to calculate moves."
          : "You will be matched automatically when another player joins."}
      </p>
    </form>
  );
};

export default JoinForm;
