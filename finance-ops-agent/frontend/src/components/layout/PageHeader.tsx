import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface PageHeaderProps {
  icon: LucideIcon
  title: string
  subtitle?: string
  actions?: React.ReactNode
  badge?: string
  iconColor?: string
  iconBg?: string
}

export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
  badge,
  iconColor = 'text-primary-600',
  iconBg = 'bg-primary-50 ring-1 ring-primary-200',
}: PageHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-surface-200 bg-white px-6 py-4 shadow-sm">
      <div className="flex items-center gap-3">
        <div className={cn('flex h-9 w-9 items-center justify-center rounded-xl', iconBg)}>
          <Icon size={18} className={iconColor} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="page-title">{title}</h1>
            {badge && (
              <span className="badge bg-primary-50 text-primary-600 ring-1 ring-primary-200 text-[10px]">
                {badge}
              </span>
            )}
          </div>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}
