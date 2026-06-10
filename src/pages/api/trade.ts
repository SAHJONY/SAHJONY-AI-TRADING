const fs = require('fs').promises;
const path = require('path');

/** API to start/stop the Trade Executor agent */
export default async function handler(req: any, res: any) {
  const statusFile = path.join(process.cwd(), 'src', 'data', 'agent-status.json');
  if (req.method === 'POST') {
    const { action } = req.body;
    const data = JSON.parse(await fs.readFile(statusFile, 'utf-8'));
    if (action === 'start') data.trade = 'active';
    else if (action === 'stop') data.trade = 'idle';
    await fs.writeFile(statusFile, JSON.stringify(data, null, 2));
    res.status(200).json({ status: data.trade });
    return;
  }
  const data = JSON.parse(await fs.readFile(statusFile, 'utf-8'));
  res.status(200).json({ status: data.trade });
}
