import { promises as fs } from 'fs';
import * as path from 'path';

export async function GET() {
  try {
    // Look for the JSON file in multiple possible locations
  const possiblePaths = [
    path.resolve(process.cwd(), 'financial_data.json'),
    path.resolve('C:/Users/juani', 'financial_data.json'),
    path.resolve('/tmp', 'financial_data.json'),
  ];
  let dataPath = '';
  for (const p of possiblePaths) {
    try {
      await fs.access(p);
      dataPath = p;
      break;
    } catch (_) {}
  }
  if (!dataPath) throw new Error('File not found');

    const content = await fs.readFile(dataPath, 'utf-8');
    return new Response(content, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: 'Financial data not available' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
