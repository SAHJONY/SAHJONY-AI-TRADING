import type { NextApiRequest, NextApiResponse } from 'next';

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  // Simple health check – could add Supabase connectivity test here
  res.status(200).json({ success: true, message: 'ping ok' });
}
