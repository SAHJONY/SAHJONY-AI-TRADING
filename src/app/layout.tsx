import type { Metadata } from 'next'
import { Providers } from '@/components/providers'
import FloatingChatButton from '@/components/floating-chat-button'
import './globals.css'

export const metadata: Metadata = {
  title: 'Sahjony Capital — AI Trading Platform',
  description: 'Autonomous AI agents that research, analyze, and execute — 24/7.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body>
        <Providers>
                  {children}
                </Providers>
                <FloatingChatButton />
      </body>
    </html>
  )
}
