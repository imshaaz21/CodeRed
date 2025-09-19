import { FormEvent, useState } from "react";

interface JoinFormProps {
  onJoin: (displayName: string) => Promise<void>;
  busy?: boolean;
}

const JoinForm = ({ onJoin, busy = false }: JoinFormProps) => {
  const [name, setName] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await onJoin(name.trim());
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
      <button type="submit" disabled={busy}>
        {busy ? "Joining…" : "Join Lobby"}
      </button>
      <p className="hint">You will be matched automatically when another player joins.</p>
    </form>
  );
};

export default JoinForm;
