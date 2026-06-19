import { useEffect, useState } from 'react';
import io from 'socket.io-client';

const socket = io('ws://localhost:8000/ws/market');

export default function Home() {
  const [messages, setMessages] = useState<string[]>([]);

  useEffect(() => {
    socket.on('message', (msg: string) => {
      setMessages((prev) => [...prev, msg]);
    });
    return () => {
      socket.off('message');
    };
  }, []);

  return (
    <div style={{ padding: '2rem' }}>
      <h1>AI Trading Dashboard</h1>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{messages.join('\n')}</pre>
    </div>
  );
}
