import { useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { Settings, Eye, EyeOff, CheckCircle2, ExternalLink, Globe } from 'lucide-react'
import { cn } from '@/lib/utils'

function SecretInput({ label, placeholder, hint }: { label: string; placeholder: string; hint?: string }) {
  const [show, setShow] = useState(false)
  const [value, setValue] = useState('')
  return (
    <div>
      <label className="block text-xs font-medium text-surface-600 mb-1.5">{label}</label>
      <div className="relative">
        <input
          type={show ? 'text' : 'password'}
          className="input pr-10"
          placeholder={placeholder}
          value={value}
          onChange={e => setValue(e.target.value)}
        />
        <button
          type="button"
          onClick={() => setShow(v => !v)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600 transition-colors"
        >
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
      {hint && <p className="mt-1 text-[11px] text-surface-400">{hint}</p>}
    </div>
  )
}

export function SettingsPage() {
  const { t, lang, setLang } = useI18n()
  const [qboConnected, setQboConnected] = useState(false)

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Settings}
        title={t('page.settings.title')}
        subtitle={t('page.settings.subtitle')}
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5 max-w-2xl">
        {/* API Keys */}
        <div className="card p-6 space-y-4">
          <h2 className="text-sm font-semibold text-surface-900">{t('settings.api_keys')}</h2>
          <SecretInput
            label="Anthropic API Key"
            placeholder="sk-ant-api03-..."
            hint="Required — powers all AI features. Get yours at console.anthropic.com"
          />
          <SecretInput
            label="Asana API Token"
            placeholder="1/XXXXXXX..."
            hint="Optional — enables task creation in Asana"
          />
          <SecretInput
            label="Ramp API Key"
            placeholder="ramp_..."
            hint="Optional — enables expense data sync from Ramp"
          />
          <button className="btn-primary text-[13px]">
            <CheckCircle2 size={14} /> {t('common.save')} API Keys
          </button>
        </div>

        {/* QuickBooks Online */}
        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-surface-900">{t('settings.qbo')}</h2>
            {qboConnected && (
              <span className="badge bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                <CheckCircle2 size={11} className="mr-1" /> {t('common.connected')}
              </span>
            )}
          </div>

          {!qboConnected ? (
            <div className="rounded-xl border border-dashed border-surface-200 bg-surface-50 p-6 text-center space-y-3">
              <div className="text-4xl">📊</div>
              <div>
                <p className="text-sm font-semibold text-surface-900">Connect QuickBooks Online</p>
                <p className="text-xs text-surface-500 mt-1 max-w-sm mx-auto">
                  Link your QBO account to enable live auditing, transaction coding, and financial reporting.
                </p>
              </div>
              <button
                onClick={() => setQboConnected(true)}
                className="btn-primary inline-flex"
              >
                <ExternalLink size={14} /> {t('common.connect')} QuickBooks
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-3 rounded-xl bg-emerald-50 border border-emerald-200">
                <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-emerald-800">Connected: Angela's Org QBO</p>
                  <p className="text-xs text-emerald-600">Realm ID: 123456789 · Last sync: just now</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">Client ID</label>
                  <input className="input" placeholder="QBO Client ID" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">Realm ID</label>
                  <input className="input" placeholder="123456789" />
                </div>
              </div>
              <button
                onClick={() => setQboConnected(false)}
                className="btn-ghost text-red-600 hover:bg-red-50 text-[13px]"
              >
                {t('common.disconnect')}
              </button>
            </div>
          )}
        </div>

        {/* Language */}
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Globe size={16} className="text-primary-600" />
            <h2 className="text-sm font-semibold text-surface-900">{t('settings.language')}</h2>
          </div>
          <div className="flex gap-3">
            {(['en', 'es'] as const).map(l => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={cn(
                  'flex-1 rounded-xl border py-3 text-sm font-medium transition-all',
                  lang === l
                    ? 'border-primary-400 bg-primary-50 text-primary-700 ring-1 ring-primary-200'
                    : 'border-surface-200 text-surface-600 hover:border-surface-300 hover:bg-surface-50',
                )}
              >
                {l === 'en' ? '🇺🇸 English' : '🇵🇷 Español'}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
