import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/stores/appStore'
import { useI18n } from '@/lib/i18n'
import {
  LayoutDashboard, Search, Tag, ShieldCheck, CreditCard,
  UserPlus, BookOpen, ClipboardList, BarChart3, Settings,
  MessageSquare, ChevronLeft, ChevronRight, Globe,
} from 'lucide-react'

const navItems = [
  { to: '/',             labelKey: 'nav.chat',         icon: MessageSquare },
  { to: '/controller',   labelKey: 'nav.controller',   icon: LayoutDashboard },
  { to: '/audit',        labelKey: 'nav.audit',        icon: Search },
  { to: '/transactions', labelKey: 'nav.transactions', icon: Tag },
  { to: '/grants',       labelKey: 'nav.grants',       icon: ShieldCheck },
  { to: '/payments',     labelKey: 'nav.payments',     icon: CreditCard },
  { to: '/vendors',      labelKey: 'nav.vendors',      icon: UserPlus },
  { to: '/sops',         labelKey: 'nav.sops',         icon: BookOpen },
  { to: '/eod',          labelKey: 'nav.eod',          icon: ClipboardList },
] as const

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore()
  const { t, lang, setLang } = useI18n()

  return (
    <aside
      className={cn(
        'relative flex h-screen flex-col bg-surface-900 border-r border-surface-800 transition-all duration-200 ease-in-out',
        sidebarCollapsed ? 'w-[60px]' : 'w-[220px]',
      )}
    >
      {/* Logo */}
      <div className={cn(
        'flex items-center border-b border-surface-800 transition-all',
        sidebarCollapsed ? 'justify-center px-0 py-4' : 'gap-2.5 px-4 py-4',
      )}>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-600 shadow-lg shadow-primary-900/40">
          <BarChart3 size={16} className="text-white" />
        </div>
        {!sidebarCollapsed && (
          <div className="animate-fade-in overflow-hidden">
            <p className="text-sm font-semibold text-white leading-none tracking-tight">{t('app.name')}</p>
            <p className="text-[11px] text-primary-400 mt-0.5 font-medium">{t('app.tagline')}</p>
          </div>
        )}
      </div>

      {/* Toggle button */}
      <button
        onClick={toggleSidebar}
        className="absolute -right-3 top-[4.25rem] z-10 flex h-6 w-6 items-center justify-center rounded-full border border-surface-700 bg-surface-800 text-surface-400 hover:bg-surface-700 hover:text-white transition-colors shadow-md"
        aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {sidebarCollapsed
          ? <ChevronRight size={12} />
          : <ChevronLeft  size={12} />}
      </button>

      {/* Nav */}
      <nav className="sidebar-scroll flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {navItems.map(({ to, labelKey, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            title={sidebarCollapsed ? t(labelKey) : undefined}
            className={({ isActive }) =>
              cn(
                'group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-all',
                sidebarCollapsed && 'justify-center px-0',
                isActive
                  ? 'bg-primary-600 text-white shadow-sm shadow-primary-900/30'
                  : 'text-surface-400 hover:bg-surface-800 hover:text-surface-100',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={16}
                  className={cn(
                    'shrink-0 transition-colors',
                    isActive ? 'text-white' : 'text-surface-500 group-hover:text-surface-300',
                  )}
                />
                {!sidebarCollapsed && (
                  <span className="truncate animate-fade-in">{t(labelKey)}</span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Divider */}
      <div className="border-t border-surface-800" />

      {/* Settings */}
      <div className="px-2 py-2">
        <NavLink
          to="/settings"
          title={sidebarCollapsed ? t('nav.settings') : undefined}
          className={({ isActive }) =>
            cn(
              'group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-all',
              sidebarCollapsed && 'justify-center px-0',
              isActive
                ? 'bg-primary-600 text-white'
                : 'text-surface-400 hover:bg-surface-800 hover:text-surface-100',
            )
          }
        >
          {({ isActive }) => (
            <>
              <Settings size={16} className={cn(
                'shrink-0 transition-colors',
                isActive ? 'text-white' : 'text-surface-500 group-hover:text-surface-300',
              )} />
              {!sidebarCollapsed && (
                <span className="truncate animate-fade-in">{t('nav.settings')}</span>
              )}
            </>
          )}
        </NavLink>
      </div>

      {/* Language toggle + footer */}
      {!sidebarCollapsed && (
        <div className="border-t border-surface-800 px-4 py-3 animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <Globe size={12} className="text-surface-500" />
              <span className="text-[11px] text-surface-500 font-medium">{t('settings.language')}</span>
            </div>
            <div className="flex items-center rounded-md bg-surface-800 p-0.5 gap-0.5">
              <button
                onClick={() => setLang('en')}
                className={cn(
                  'rounded px-2 py-0.5 text-[11px] font-semibold transition-all',
                  lang === 'en'
                    ? 'bg-primary-600 text-white shadow-sm'
                    : 'text-surface-400 hover:text-surface-200',
                )}
              >EN</button>
              <button
                onClick={() => setLang('es')}
                className={cn(
                  'rounded px-2 py-0.5 text-[11px] font-semibold transition-all',
                  lang === 'es'
                    ? 'bg-primary-600 text-white shadow-sm'
                    : 'text-surface-400 hover:text-surface-200',
                )}
              >ES</button>
            </div>
          </div>
          <p className="text-[10px] text-surface-600 leading-none">{t('app.powered')}</p>
        </div>
      )}

      {/* Language (collapsed) */}
      {sidebarCollapsed && (
        <div className="border-t border-surface-800 py-2 flex justify-center">
          <button
            onClick={() => setLang(lang === 'en' ? 'es' : 'en')}
            title={lang === 'en' ? 'Switch to Español' : 'Switch to English'}
            className="flex h-7 w-7 items-center justify-center rounded-md bg-surface-800 text-[10px] font-bold text-surface-400 hover:bg-primary-600 hover:text-white transition-all"
          >
            {lang.toUpperCase()}
          </button>
        </div>
      )}
    </aside>
  )
}
