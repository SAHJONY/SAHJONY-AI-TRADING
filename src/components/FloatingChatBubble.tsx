'use client';

import { useState, useEffect } from 'react';

// Owner email – replace with env/config if needed
const OWNER_EMAIL = 'sahjonycapitalllc@outlook.com';

export default function FloatingChatBubble() {
  const [open, setOpen] = useState(false);
  const [isOwner, setIsOwner] = useState(false);

  useEffect(() => {
    // Enable for owner preview; set NEXT_PUBLIC_SHOW_OWNER_CHAT=false to hide
    const env = process.env.NEXT_PUBLIC_SHOW_OWNER_CHAT;
    if (env === 'true') {
      setIsOwner(true);
    } else if (env === undefined) {
      // default to visible in dev/owner preview
      setIsOwner(true);
    }
  }, []);

  if (!isOwner) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <button
        onClick={() => setOpen(!open)}
        className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-full p-4 shadow-lg flex items-center justify-center"
      >
        💬
      </button>
      {open && (
        <div className="mt-2 w-80 h-96 bg-gray-800 text-white rounded-lg shadow-xl flex flex-col">
          <div className="flex-1 p-2 overflow-y-auto">
            {/* Placeholder chat area – replace with real chat UI */}
            <p className="text-gray-400">Owner chat window (dev only)</p>
          </div>
          <input
            type="text"
            placeholder="Message…"
            className="w-full border-t border-gray-700 p-2 bg-gray-900 text-white placeholder-gray-500"
          />
        </div>
      )}
    </div>
  );
}
