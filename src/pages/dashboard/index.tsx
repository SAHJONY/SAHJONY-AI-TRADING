import React, { useEffect, useState } from 'react';

type AgentStatus = 'active' | 'idle' | 'stopped';

const fetchStatus = async (agent: string): Promise<AgentStatus> => {
  const res = await fetch(`/api/${agent}`);
  const data = await res.json();
  return data.status as AgentStatus;
};

const toggleAgent = async (agent: string, action: 'start' | 'stop') => {
  await fetch(`/api/${agent}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
};

const Dashboard: React.FC = () => {
  const [market, setMarket] = useState<AgentStatus>('idle');
  const [risk, setRisk] = useState<AgentStatus>('idle');
  const [trade, setTrade] = useState<AgentStatus>('idle');

  const load = async () => {
    setMarket(await fetchStatus('market'));
    setRisk(await fetchStatus('risk'));
    setTrade(await fetchStatus('trade'));
  };

  useEffect(() => {
    load();
    const i = setInterval(load, 5000);
    return () => clearInterval(i);
  }, []);

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>Ultra‑Premium AI Agentic Dashboard</h1>
      <div style={{ display: 'flex', gap: '20px' }}>
        <AgentPanel title="Market Scout" status={market} onToggle={setMarket} agent="market" />
        <AgentPanel title="Risk Manager" status={risk} onToggle={setRisk} agent="risk" />
        <AgentPanel title="Trade Executor" status={trade} onToggle={setTrade} agent="trade" />
      </div>
    </div>
  );
};

interface AgentPanelProps {
  title: string;
  status: AgentStatus;
  onToggle: (newStatus: AgentStatus) => void;
  agent: string;
}

const AgentPanel: React.FC<AgentPanelProps> = ({ title, status, onToggle, agent }) => {
  const isActive = status === 'active';
  const handle = async () => {
    const action = isActive ? 'stop' : 'start';
    await toggleAgent(agent, action as any);
    const newStatus = await fetchStatus(agent);
    onToggle(newStatus);
  };
  return (
    <div style={{ border: '1px solid #aaa', borderRadius: '8px', padding: '15px', width: '200px' }}>
      <h2>{title}</h2>
      <p>Status: <strong>{status}</strong></p>
      <button onClick={handle}>{isActive ? 'Stop' : 'Start'}</button>
    </div>
  );
};

export default Dashboard;
