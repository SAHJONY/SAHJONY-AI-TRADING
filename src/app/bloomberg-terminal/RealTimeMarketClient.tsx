'use client';
import { useEffect, useState } from 'react';

export default function RealTimeMarketClient() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const res = await fetch('/api/financial-data');
      if (!res.ok) throw new Error('Failed to fetch');
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // poll every 5s
    return () => clearInterval(interval);
  }, []);

  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!data) return <div>Loading market data...</div>;

  // Assuming data is an object with symbol keys
  const rows = Object.entries(data).map(([symbol, info]) => (
    <tr key={symbol}>
      <td className="px-2 py-1 border">{symbol}</td>
      <td className="px-2 py-1 border">{info.price ?? ''}</td>
      <td className="px-2 py-1 border">{info.change ?? ''}</td>
      <td className="px-2 py-1 border">{info.percent ?? ''}</td>
    </tr>
  ));

  return (
    <div className="overflow-auto mb-6">
      <h2 className="text-xl font-semibold mb-2">Live Market Snapshot</h2>
      <table className="min-w-full table-auto border-collapse">
        <thead>
          <tr className="bg-gray-700">
            <th className="px-2 py-1 border">Symbol</th>
            <th className="px-2 py-1 border">Price</th>
            <th className="px-2 py-1 border">Change</th>
            <th className="px-2 py-1 border">% Change</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  );
}
