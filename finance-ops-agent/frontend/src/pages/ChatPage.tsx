import { useRef, useEffect, useState, useCallback } from 'react'
import { MessageBubble } from '@/components/ui/MessageBubble'
import { useChatStore } from '@/stores/chatStore'
import { streamChat, type AgentModule } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useI18n } from '@/lib/i18n'
import {
  Send, Paperclip, RotateCcw, ChevronDown,
  Loader2, MessageSquare, Zap,
} from 'lucide-react'

const MODULES: AgentModule[] = [
  'orchestrator', 'qbo_auditor', 'transaction_coder', 'grant_compliance',
  'payment_request', 'vendor_onboarding', 'sop_builder', 'eod_report', 'controller',
]

type QuickPromptKey =
  | 'qp.audit'   | 'qp.audit.desc'
  | 'qp.code'    | 'qp.code.desc'
  | 'qp.grants'  | 'qp.grants.desc'
  | 'qp.morning' | 'qp.morning.desc'
  | 'qp.eod'     | 'qp.eod.desc'
  | 'qp.sop'     | 'qp.sop.desc'

const QP_PAIRS: { labelKey: QuickPromptKey; promptKey: QuickPromptKey }[] = [
  { labelKey: 'qp.audit',   promptKey: 'qp.audit.desc'   },
  { labelKey: 'qp.code',    promptKey: 'qp.code.desc'    },
  { labelKey: 'qp.grants',  promptKey: 'qp.grants.desc'  },
  { labelKey: 'qp.morning', promptKey: 'qp.morning.desc' },
  { labelKey: 'qp.eod',     promptKey: 'qp.eod.desc'     },
  { labelKey: 'qp.sop',     promptKey: 'qp.sop.desc'     },
]

type ModuleKey =
  | 'module.orchestrator' | 'module.qbo_auditor' | 'module.transaction_coder'
  | 'module.grant_compliance' | 'module.payment_request' | 'module.vendor_onboarding'
  | 'module.sop_builder' | 'module.eod_report' | 'module.controller'

const MODULE_KEY_MAP: Record<AgentModule, ModuleKey> = {
  orchestrator:     'module.orchestrator',
  qbo_auditor:      'module.qbo_auditor',
  transaction_coder:'module.transaction_coder',
  grant_compliance: 'module.grant_compliance',
  payment_request:  'module.payment_request',
  vendor_onboarding:'module.vendor_onboarding',
  sop_builder:      'module.sop_builder',
  eod_report:       'module.eod_report',
  controller:       'module.controller',
}

export function ChatPage() {
  const {
    messages, activeModule, isStreaming, conversationId,
    setModule, addMessage, updateMessage, appendStreamChunk,
    setStreaming, clearConversation,
  } = useChatStore()

  const { t } = useI18n()
  const [input, setInput] = useState('')
  const [moduleOpen, setModuleOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef  = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || isStreaming) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    addMessage({ role: 'user', content })

    const assistantId = addMessage({
      role: 'assistant',
      content: '',
      module: activeModule,
      isStreaming: true,
    })

    setStreaming(true)
    abortRef.current = new AbortController()

    try {
      for await (const event of streamChat(
        { message: content, module: activeModule, conversation_id: conversationId ?? undefined },
        abortRef.current.signal,
      )) {
        if (event.type === 'routing' && event.module) {
          updateMessage(assistantId, { module: event.module })
        } else if (event.type === 'token' && event.content) {
          appendStreamChunk(assistantId, event.content)
        } else if (event.type === 'done') {
          break
        } else if (event.type === 'error') {
          appendStreamChunk(assistantId, `\n\n⚠️ Error: ${event.detail}`)
          break
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        appendStreamChunk(assistantId, '\n\n⚠️ Connection error. Please try again.')
      }
    } finally {
      updateMessage(assistantId, { isStreaming: false })
      setStreaming(false)
    }
  }, [input, isStreaming, activeModule, conversationId, addMessage, updateMessage, appendStreamChunk, setStreaming])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Auto-resize textarea
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-surface-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-50 ring-1 ring-primary-200">
            <MessageSquare size={14} className="text-primary-600" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-surface-900 leading-none">{t('chat.title')}</h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Module selector */}
          <div className="relative">
            <button
              onClick={() => setModuleOpen(v => !v)}
              className="flex items-center gap-2 rounded-lg border border-surface-200 bg-white px-3 py-1.5 text-xs font-medium text-surface-700 hover:border-surface-300 hover:bg-surface-50 transition-colors shadow-sm"
            >
              <Zap size={11} className="text-primary-500" />
              {t(MODULE_KEY_MAP[activeModule])}
              <ChevronDown size={11} className="text-surface-400" />
            </button>

            {moduleOpen && (
              <div className="absolute right-0 top-full z-50 mt-1.5 w-56 rounded-xl border border-surface-200 bg-white py-1.5 shadow-card-lg animate-fade-in">
                <p className="px-3 pb-1.5 pt-0.5 text-[10px] font-semibold uppercase tracking-wider text-surface-400">
                  {t('chat.module')}
                </p>
                {MODULES.map(m => (
                  <button
                    key={m}
                    onClick={() => { setModule(m); setModuleOpen(false) }}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors',
                      m === activeModule
                        ? 'bg-primary-50 text-primary-700 font-medium'
                        : 'text-surface-600 hover:bg-surface-50',
                    )}
                  >
                    {m === activeModule && (
                      <span className="h-1.5 w-1.5 rounded-full bg-primary-500 shrink-0" />
                    )}
                    {m !== activeModule && (
                      <span className="h-1.5 w-1.5 rounded-full bg-transparent shrink-0" />
                    )}
                    {t(MODULE_KEY_MAP[m])}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={clearConversation}
            title={t('chat.clear')}
            className="rounded-lg p-1.5 text-surface-400 hover:bg-surface-100 hover:text-surface-700 transition-colors"
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </header>

      {/* ── Messages ────────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-8 animate-fade-in">
            {/* Hero */}
            <div className="text-center space-y-3">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-600 shadow-card-lg shadow-primary-200">
                <BarChart3Icon />
              </div>
              <h2 className="text-xl font-semibold text-surface-900">{t('chat.empty.title')}</h2>
              <p className="text-sm text-surface-500 max-w-md leading-relaxed">
                {t('chat.empty.desc')}
              </p>
            </div>

            {/* Quick prompts */}
            <div className="grid grid-cols-2 gap-2.5 w-full max-w-xl">
              {QP_PAIRS.map(({ labelKey, promptKey }) => (
                <button
                  key={labelKey}
                  onClick={() => handleSend(t(promptKey as Parameters<typeof t>[0]))}
                  className="card rounded-xl px-4 py-3 text-left hover:border-primary-300 hover:shadow-card-md transition-all group"
                >
                  <span className="block text-xs font-semibold text-surface-800 group-hover:text-primary-700 mb-1">
                    {t(labelKey as Parameters<typeof t>[0])}
                  </span>
                  <span className="text-[11px] text-surface-400 line-clamp-2 leading-relaxed">
                    {t(promptKey as Parameters<typeof t>[0])}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.length > 0 && (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ───────────────────────────────────────────────────────────── */}
      <div className="border-t border-surface-200 bg-white px-6 py-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-3 rounded-xl border border-surface-200 bg-surface-50 px-4 py-3 focus-within:border-primary-400 focus-within:bg-white focus-within:shadow-sm transition-all">
            <button className="mb-0.5 text-surface-400 hover:text-surface-600 transition-colors">
              <Paperclip size={16} />
            </button>

            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              rows={1}
              placeholder={t('chat.placeholder')}
              className="flex-1 resize-none bg-transparent text-sm text-surface-900 placeholder-surface-400 outline-none"
              disabled={isStreaming}
            />

            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming}
              className={cn(
                'mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all',
                input.trim() && !isStreaming
                  ? 'bg-primary-600 text-white hover:bg-primary-700 shadow-sm'
                  : 'text-surface-300 cursor-not-allowed',
              )}
            >
              {isStreaming
                ? <Loader2 size={14} className="animate-spin" />
                : <Send size={14} />
              }
            </button>
          </div>

          <p className="mt-2 text-center text-[11px] text-surface-400">
            {t('chat.module')}: <span className="text-surface-600 font-medium">{t(MODULE_KEY_MAP[activeModule])}</span>
            {' · '}
            {t('chat.hint')}
          </p>
        </div>
      </div>
    </div>
  )
}

// Small inline icon to avoid import issues
function BarChart3Icon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6"  y1="20" x2="6"  y2="14" />
    </svg>
  )
}
