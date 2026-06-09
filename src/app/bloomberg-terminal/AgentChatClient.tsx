'use client';
import { useState } from 'react';

export default function AgentChatClient() {
  const [command, setCommand] = useState('');
  const [response, setResponse] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const sendCommand = async () => {
    if (!command) return;
    setLoading(true);
    try {
      const res = await fetch('/api/agents/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      });
      const data = await res.json();
      setResponse(data.result || JSON.stringify(data));
    } catch (e: any) {
      setResponse(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-6">
      <h2 className="text-xl font-semibold mb-2">Agent Command Console</h2>
      <div className="flex gap-2 mb-2">
        <input
          type="text"
          className="flex-1 px-2 py-1 border rounded bg-gray-800 text-white"
          placeholder="Enter command for AI agents"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
        />
        <button
          className="px-4 py-1 bg-primary text-white rounded disabled:opacity-50"
          disabled={loading}
          onClick={sendCommand}
        >
          {loading ? 'Sending...' : 'Send'}
        </button>
      </div>
      {response && (
        <pre className="bg-gray-900 p-2 rounded whitespace-pre-wrap">{response}</pre>
      )}
    </div>
  );
}
