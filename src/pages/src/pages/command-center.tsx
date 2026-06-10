import React, { useEffect, useState } from 'react';
import { ArrowRight, Circle } from 'lucide-react';

type AgentStatus = 'active' | 'idle' | 'stopped';

type Metrics = {
  timestamp: number;
  totalTrades: number;
  profit: string;
  marketPrice: string;
  agents: { market: AgentStatus; risk: AgentStatus; trade: AgentStatus };
};

const CommandCenter: React.FC = () => {
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    const es = new EventSource('/api/metrics');
    es.onmessage = e => {
      try {
        const data = JSON.parse(e.data) as Metrics;
        setMetrics(data);
      } catch (_) {}
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, []);

  const toggleAgent = async (agent: string, action: 'start' | 'stop') => {
    await fetch(`/api/${agent}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });
  };

  return (
    <div className="relative min-h-screen bg-background text-primary p-6">
        <div className="cinematic-orb absolute -top-40 -left-20 w-96 h-96 bg-orb-blue" />
        <div className="cinematic-orb absolute -bottom-32 -right-24 w-80 h-80 bg-orb-purple" />
        <div className="cinematic-orb absolute top-1/2 left-1/4 w-64 h-64 bg-orb-gold" />
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-4xl gradient-text">CEO Command Center</h1>
        <button onClick={() => window.location.reload()} className="flex items-center gap-2 rounded tesla bg-primary px-4 py-2 text-white hover:bg-primary-hover">
          <ArrowRight size={16} /> Refresh
        </button>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <StatCard title="Total Trades" value={metrics?.totalTrades?.toString() ?? '--'} />
        <StatCard title="Profit (USD)" value={metrics ? `$${metrics.profit}` : '--'} />
        <StatCard title="Market Price" value={metrics ? `$${metrics.marketPrice}` : '--'} />
      </section>


      <section className="mb-8"><iframe src="/admin-dashboard" className="w-full h-[800px] border-none rounded" title="Admin Dashboard"></iframe></section>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <AgentPanel title="Market Scout" status={metrics?.agents.market ?? 'idle'} agent="market" onToggle={toggleAgent} />
        <AgentPanel title="Risk Manager" status={metrics?.agents.risk ?? 'idle'} agent="risk" onToggle={toggleAgent} />
        <AgentPanel title="Trade Executor" status={metrics?.agents.trade ?? 'idle'} agent="trade" onToggle={toggleAgent} />
      </section>
    </div>
  );
};

interface StatCardProps { title: string; value: string; }
const StatCard: React.FC<StatCardProps> = ({ title, value }) => (
  <div className="rounded glass glass-heavy p-4 shadow-primary">
    <h2 className="gradient-text mb-2">{title}</h2>
    <p className="text-2xl font-mono">{value}</p>
  </div>
);

interface AgentPanelProps { title: string; status: AgentStatus; agent: string; onToggle: (agent: string, action: 'start' | 'stop') => Promise<void>; }
const AgentPanel: React.FC<AgentPanelProps> = ({ title, status, agent, onToggle }) => {
  const isActive = status === 'active';
  const handle = async () => { await onToggle(agent, isActive ? 'stop' : 'start'); };
  return (
    <div className="rounded glass glass-heavy p-4 shadow-primary">
      <h2 className="gradient-text mb-2 flex items-center gap-2"><Circle size={16} className={isActive ? 'text-success' : 'text-muted'} /> {title}</h2>
      <p className="mb-3">Status: <span className="font-mono">{status}</span></p>
      <button onClick={handle} className="px-3 py-1 bg-primary hover:bg-primary-hover text-white rounded tesla">{isActive ? 'Stop' : 'Start'}</button>
    </div>
  );
};

export default CommandCenter;
