import { createClient } from '@/lib/supabase/server';
import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic'; // Force server‑side rendering each request

export default async function BloombergTerminalPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user || user.email !== 'sahjonycapitalllc@outlook.com') {
    redirect('/owner-login');
  }

  return (
    <div className="min-h-screen bg-background text-white p-4">
      <h1 className="text-3xl font-bold mb-4">AI Agentic Bloomberg Terminal</h1>
      <RealTimeMarket />
      <AgentChat />
    </div>
  );
}

// ---------------------------------------------------
// Real‑time market component (client side)
// ---------------------------------------------------
import RealTimeMarketClient from './RealTimeMarketClient';
import AgentChatClient from './AgentChatClient';

function RealTimeMarket() {
  // This component runs in the browser – use 'use client'
  return <RealTimeMarketClient />;
}

// ---------------------------------------------------
// Agent chat component (client side)
// ---------------------------------------------------
function AgentChat() {
  return <AgentChatClient />;
}
