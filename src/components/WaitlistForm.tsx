import { useState } from "react";

export const WaitlistForm: React.FC = () => {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus(null);
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });
      if (res.ok) {
        setStatus("Thanks! We'll keep you posted.");
        setEmail("");
      } else {
        setStatus("Oops, something went wrong.");
      }
    } catch (err) {
      setStatus("Network error.");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <input
        type="email"
        placeholder="Your email"
        required
        value={email}
        onChange={e => setEmail(e.target.value)}
        className="px-4 py-2 rounded bg-white/10 backdrop-blur-sm text-white placeholder-gray-300 border border-white/20 focus:outline-none"
      />
      <button
        type="submit"
        className="px-4 py-2 bg-primary hover:bg-primary/80 text-white rounded transition"
      >
        Join Waitlist
      </button>
      {status && <p className="mt-2 text-sm text-white/80">{status}</p>}
    </form>
  );
};
