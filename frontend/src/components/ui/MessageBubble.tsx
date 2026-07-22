import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn, formatDate } from '@/lib/utils'
import type { Message } from '@/stores/chatStore'
import { useI18n } from '@/lib/i18n'
import { Bot, User, Wrench } from 'lucide-react'
import type { AgentModule } from '@/lib/api'

type ModuleKey =
  | 'module.orchestrator' | 'module.qbo_auditor' | 'module.transaction_coder'
  | 'module.grant_compliance' | 'module.payment_request' | 'module.vendor_onboarding'
  | 'module.sop_builder' | 'module.eod_report' | 'module.controller'
  | 'module.bank_reconciliation' | 'module.payroll_allocation'

const MODULE_KEY_MAP: Record<AgentModule, ModuleKey> = {
  orchestrator:        'module.orchestrator',
  qbo_auditor:         'module.qbo_auditor',
  transaction_coder:   'module.transaction_coder',
  grant_compliance:    'module.grant_compliance',
  payment_request:     'module.payment_request',
  vendor_onboarding:   'module.vendor_onboarding',
  sop_builder:         'module.sop_builder',
  eod_report:          'module.eod_report',
  controller:          'module.controller',
  bank_reconciliation: 'module.bank_reconciliation',
  payroll_allocation:  'module.payroll_allocation',
}

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'
  const { t } = useI18n()

  return (
    <div className={cn('flex gap-3 animate-slide-up', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-sm',
          isUser
            ? 'bg-primary-600'
            : 'bg-white border border-surface-200',
        )}
      >
        {isUser
          ? <User size={14} className="text-white" />
          : <Bot  size={14} className="text-surface-500" />
        }
      </div>

      {/* Bubble */}
      <div className={cn('max-w-[78%] space-y-1.5', isUser && 'items-end flex flex-col')}>
        {/* Module badge (assistant only) */}
        {!isUser && message.module && (
          <div className="flex items-center gap-1.5">
            <span className="badge bg-primary-50 text-primary-700 ring-1 ring-primary-200">
              {t(MODULE_KEY_MAP[message.module])}
            </span>
            {message.tool_calls && message.tool_calls.length > 0 && (
              <span className="inline-flex items-center gap-1 text-[11px] text-surface-400">
                <Wrench size={10} />
                {message.tool_calls.join(', ')}
              </span>
            )}
          </div>
        )}

        {/* Content */}
        <div
          className={cn(
            'rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm',
            isUser
              ? 'bg-primary-600 text-white rounded-tr-none'
              : 'bg-white border border-surface-200 text-surface-800 rounded-tl-none',
            message.isStreaming && 'after:ml-0.5 after:animate-pulse-soft after:content-["▋"] after:text-primary-500',
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="prose prose-sm max-w-none
                prose-headings:font-semibold prose-headings:text-surface-900 prose-headings:tracking-tight
                prose-p:text-surface-700 prose-p:leading-relaxed
                prose-code:bg-surface-100 prose-code:text-primary-700 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-[12px] prose-code:font-mono
                prose-pre:bg-surface-900 prose-pre:text-surface-100 prose-pre:rounded-lg prose-pre:text-[12px]
                prose-table:text-xs prose-th:text-surface-600 prose-td:text-surface-700
                prose-a:text-primary-600 prose-a:no-underline hover:prose-a:underline
                prose-strong:text-surface-900 prose-strong:font-semibold
                prose-li:text-surface-700
                prose-blockquote:border-primary-300 prose-blockquote:text-surface-600"
            >
              {message.content || '…'}
            </ReactMarkdown>
          )}
        </div>

        <p className={cn('text-[11px] text-surface-400', isUser && 'text-right')}>
          {formatDate(message.timestamp)}
        </p>
      </div>
    </div>
  )
}
