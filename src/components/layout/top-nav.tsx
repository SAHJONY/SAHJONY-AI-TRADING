'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth, useTheme } from '@/components/providers'
import { Menu, LogOut, Settings, MessageSquare, Sun, Moon, TrendingUp, Activity, Cpu, DollarSign, Globe } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

export const navLinks = [
  { href: '/agents', label: 'Agents', icon: Activity },
  { href: '/providers', label: 'Providers', icon: Cpu },
  { href: '/trading', label: 'Trading', icon: TrendingUp },
  { href: '/markets', label: 'Markets', icon: Globe },
  { href: '/funding', label: 'Funding', icon: DollarSign },
  { href: '/conversations', label: 'Conversations', icon: MessageSquare },
  { href: '/owner-login', label: 'Owner', icon: Settings },
  { href: '/env', label: 'Env', icon: Settings },
]

export function TopNav() {
  const { user, signOut } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const pathname = usePathname() ?? ''
  const [menuOpen, setMenuOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  return (
    <header className="border-b border-border/50 bg-background/60 backdrop-blur-2xl sticky top-0 z-50">
      <div className="container-custom flex h-14 items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <div className="relative">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center group-hover:shadow-primary transition-all duration-300">
              <span className="text-white font-display font-bold text-sm">S</span>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-display font-bold text-lg text-white tracking-tesla">SAHJONY</span>
            <span className="hidden sm:block text-[10px] text-text-muted uppercase tracking-[0.2em]">Capital</span>
          </div>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-1">
          {navLinks.map((link) => {
            const isActive = pathname.startsWith(link.href)
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  'flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-300',
                  isActive
                    ? 'text-white bg-white/[0.06]'
                    : 'text-text-secondary hover:text-white hover:bg-white/[0.03]'
                )}
              >
                <link.icon className="h-3.5 w-3.5" />
                {link.label}
              </Link>
            )
          })}
          <Link
            href="/pricing"
            className={cn(
              'flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-300',
              pathname.startsWith('/pricing')
                ? 'text-white bg-white/[0.06]'
                : 'text-text-secondary hover:text-white hover:bg-white/[0.03]'
            )}
          >
            Pricing
          </Link>
        </nav>

        {/* Right side */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-full hover:bg-white/[0.04] transition-all duration-300"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? (
              <Moon className="h-4 w-4 text-text-muted hover:text-white transition-colors" />
            ) : (
              <Sun className="h-4 w-4 text-text-muted hover:text-white transition-colors" />
            )}
          </button>

          {user ? (
            <>
              <div className="relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-2 p-1 rounded-full hover:bg-white/[0.04] transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-white/[0.06] flex items-center justify-center text-white font-medium text-xs border border-border/50">
                    {user.email?.[0]?.toUpperCase() || 'U'}
                  </div>
                </button>

                {userMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setUserMenuOpen(false)}
                    />
                    <div className="absolute right-0 mt-2 w-56 py-1 bg-surface-elevated border border-border rounded-2xl shadow-2xl z-50 animate-scale-in overflow-hidden">
                      <div className="px-4 py-3 border-b border-border">
                        <p className="text-sm font-medium text-white truncate">{user.email}</p>
                      </div>
                      <div className="py-1">
                        <Link
                          href="/settings"
                          className="flex items-center gap-3 px-4 py-2.5 text-sm text-text-secondary hover:text-white hover:bg-white/[0.03] transition-colors"
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
                          className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-text-secondary hover:text-error hover:bg-error/5 transition-colors"
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
                className="px-4 py-1.5 text-sm text-text-secondary hover:text-white transition-colors"
              >
                Sign in
              </Link>
              <Link
                href="/login"
                className="px-5 py-1.5 text-sm bg-primary text-white rounded-full font-medium hover:bg-primary-hover hover:shadow-primary transition-all duration-300"
              >
                Get Started
              </Link>
            </>
          )}

          {/* Mobile menu button */}
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="md:hidden p-2 text-text-muted hover:text-white hover:bg-white/[0.04] rounded-full transition-colors"
          >
            <Menu className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden border-t border-border/50 bg-surface-elevated/95 backdrop-blur-xl animate-slide-down">
          <nav className="container-custom py-2 space-y-0.5">
            {navLinks.map((link) => {
              const isActive = pathname.startsWith(link.href)
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className={cn(
                    'flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all',
                    isActive
                      ? 'text-white bg-white/[0.06]'
                      : 'text-text-secondary hover:text-white hover:bg-white/[0.03]'
                  )}
                >
                  <link.icon className="h-4 w-4" />
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
