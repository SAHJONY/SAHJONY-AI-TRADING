'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth, useTheme } from '@/components/providers'
import { Bot, Menu, LogOut, Settings, MessageSquare, Zap, Sun, Moon, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

const navLinks = [
  { href: '/agents', label: 'Agents', icon: Bot },
  { href: '/trading', label: 'Trading', icon: TrendingUp },
  { href: '/conversations', label: 'Conversations', icon: MessageSquare },
  { href: '/pricing', label: 'Pricing', icon: Zap },
]

export function TopNav() {
  const { user, signOut } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const pathname = usePathname()
  const [menuOpen, setMenuOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  return (
    <header className="border-b border-border bg-background/80 backdrop-blur-md sticky top-0 z-50">
      <div className="container-custom flex h-16 items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <div className="relative">
            <div className="p-2 rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-all duration-200">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-success rounded-full border-2 border-background" />
          </div>
          <div>
            <span className="font-bold text-xl gradient-text">SAHJONY</span>
            <span className="hidden sm:block text-xs text-zinc-500 -mt-0.5">AI Agent Platform</span>
          </div>
        </Link>

        {/* Desktop Nav Links */}
        <nav className="hidden md:flex items-center gap-1">
          {navLinks.map((link) => {
            const isActive = pathname.startsWith(link.href)
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-zinc-400 hover:text-white hover:bg-surface'
                )}
              >
                <link.icon className="h-4 w-4" />
                {link.label}
              </Link>
            )
          })}
        </nav>

        {/* Right side */}
        <div className="flex items-center gap-2">
          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="relative p-2.5 rounded-xl hover:bg-surface transition-all duration-200 group"
            aria-label="Toggle theme"
          >
            <div className="relative w-5 h-5">
              {theme === 'dark' ? (
                <Moon className="h-5 w-5 text-zinc-400 group-hover:text-white transition-all duration-300" />
              ) : (
                <Sun className="h-5 w-5 text-zinc-400 group-hover:text-white transition-all duration-300" />
              )}
            </div>
          </button>

          {user ? (
            <>
              {/* User Avatar Button */}
              <div className="relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-2 p-1.5 rounded-xl hover:bg-surface transition-colors"
                >
                  <div className="w-9 h-9 rounded-xl bg-primary/20 flex items-center justify-center text-primary font-semibold text-sm">
                    {user.email?.[0]?.toUpperCase() || 'U'}
                  </div>
                  <span className="hidden sm:block text-sm text-zinc-400">{user.email?.split('@')[0]}</span>
                </button>

                {userMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setUserMenuOpen(false)}
                    />
                    <div className="absolute right-0 mt-2 w-56 py-2 bg-surface-elevated border border-border rounded-xl shadow-xl z-50 animate-scale-in">
                      <div className="px-4 py-3 border-b border-border">
                        <p className="text-sm font-medium text-white truncate">{user.email}</p>
                      </div>
                      <div className="py-1">
                        <Link
                          href="/settings"
                          className="flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-300 hover:bg-surface hover:text-white transition-colors"
                          onClick={() => setUserMenuOpen(false)}
                        >
                          <Settings className="h-4 w-4" />
                          Settings
                        </Link>
                        <button
                          onClick={() => {
                            setUserMenuOpen(false)
                            signOut()
                          }}
                          className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-300 hover:bg-surface hover:text-error transition-colors"
                        >
                          <LogOut className="h-4 w-4" />
                          Sign out
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="px-4 py-2 text-sm text-zinc-300 hover:text-white transition-colors"
              >
                Sign in
              </Link>
              <Link
                href="/login"
                className="px-5 py-2.5 text-sm bg-primary text-white rounded-lg font-medium hover:bg-primary-hover hover:shadow-primary transition-all"
              >
                Get Started
              </Link>
            </>
          )}

          {/* Mobile menu button */}
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="md:hidden p-2 text-zinc-400 hover:text-white hover:bg-surface rounded-lg transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden border-t border-border bg-surface-elevated animate-slide-down">
          <nav className="container-custom py-3 space-y-1">
            {navLinks.map((link) => {
              const isActive = pathname.startsWith(link.href)
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all',
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-zinc-400 hover:text-white hover:bg-surface'
                  )}
                >
                  <link.icon className="h-5 w-5" />
                  {link.label}
                </Link>
              )
            })}
          </nav>
        </div>
      )}
    </header>
  )
}