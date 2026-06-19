import React from 'react';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <title>AI Trading Dashboard</title>
      </head>
      <body>{children}</body>
    </html>
  );
}
