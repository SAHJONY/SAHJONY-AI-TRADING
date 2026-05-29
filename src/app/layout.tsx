import type { Metadata } from 'next'
import './globals.css'
import { Providers } from '@/components/providers'
import { ToastContainer } from '@/components/ui/toast'

export const metadata: Metadata = {
  title: 'SAHJONY - AI Agent Platform',
  description: 'Build, deploy, and manage intelligent AI agents powered by Hermes and Freebuff',
  icons: {
    icon: '/favicon.ico',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background antialiased">
        <Providers>{children}</Providers>
        <ToastContainer />
      </body>
    </html>
  )
}