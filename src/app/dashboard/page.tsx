import React from 'react';

export default function Dashboard() {
  return (
    <div className="relative min-h-screen bg-gray-900 text-white overflow-hidden">
      {/* Standard UI background */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url('https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1920&q=80')" }}
      />
      {/* Dark overlay for readability */}
      <div className="absolute inset-0 bg-gradient-to-b from-black via-transparent to-black opacity-70" />

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-4 text-center">
        <h1 className="text-5xl md:text-7xl font-extrabold mb-6" style={{ fontFamily: "'Orbitron', sans-serif" }}>
          Sahjony Capital – Institutional AI Trading Dashboard
        </h1>
        <p className="text-xl md:text-2xl max-w-2xl mb-8">
          Institution‑grade AI‑driven market insights, ultra‑low‑latency multi‑exchange execution, and automated risk management, all within a sleek, cinematic interface.
        </p>
        <a
          href="/dashboard"
          className="inline-block bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-semibold py-3 px-8 rounded-full shadow-lg transform hover:scale-105 transition"
        >
          Enter Dashboard
        </a>
      </div>
    </div>
  );
}
