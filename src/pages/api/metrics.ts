const fs = require('fs').promises;
const path = require('path');

/** SSE endpoint that streams current platform metrics */
export default async function handler(_req: any, res: any) {
  const statusFile = path.join(process.cwd(), 'src', 'data', 'agent-status.json');
  // Enable Server‑Sent Events (SSE)
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.(); // ensure headers are sent immediately

  const sendMetrics = async () => {
    const dataFile = JSON.parse(await fs.readFile(statusFile, 'utf-8'));
    const data = {
      timestamp: Date.now(),
      totalTrades: dataFile.totalTrades,
      profit: dataFile.profit,
      marketPrice: dataFile.marketPrice,
      agents: {
        market: dataFile.market,
        risk: dataFile.risk,
        trade: dataFile.trade,
      },
    };
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  };

  // First payload
  await sendMetrics();
  const interval = setInterval(() => {
    sendMetrics().catch(() => {});
  }, 3000);

  // Cleanup when client disconnects
  res.on('close', () => {
    clearInterval(interval);
    res.end();
  });
}
