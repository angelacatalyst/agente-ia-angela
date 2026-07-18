import { useEffect, useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api } from '@/lib/api'
import type { QBOCompany } from '@/lib/api'
import { Settings, Eye, EyeOff, CheckCircle2, ExternalLink, Globe, Building2, RefreshCw, AlertCircle } from 'lucide-react'
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

function CompanyCard({ company, isSelected, onSelect }: {
  company: QBOCompany
  isSelected: boolean
  onSelect: () => void
}) {
  const expired = company.token_expired
  return (
    <button
      onClick={onSelect}
      className={cn(
        'w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-all',
        isSelected
          ? 'border-primary-300 bg-primary-50 ring-1 ring-primary-200'
          : 'border-surface-200 bg-white hover:border-surface-300 hover:bg-surface-50',
      )}
    >
      <div className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
        expired ? 'bg-amber-50' : 'bg-emerald-50',
      )}>
        <Building2 size={16} className={expired ? 'text-amber-500' : 'text-emerald-600'} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-surface-900 truncate">{company.company_name}</p>
        <p className="text-[11px] text-surface-400 truncate">Realm: {company.realm_id}</p>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        {expired ? (
          <span className="flex items-center gap-1 text-[10px] font-semibold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full ring-1 ring-amber-200">
            <AlertCircle size={9} /> Token expired
          </span>
        ) : (
          <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full ring-1 ring-emerald-200">
            <CheckCircle2 size={9} /> Connected
          </span>
        )}
        {isSelected && (
          <span className="text-[10px] font-bold text-primary-600">Active</span>
        )}
      </div>
    </button>
  )
}

export function SettingsPage() {
  const { t, lang, setLang } = useI18n()
  const { companies, selectedRealmId, setCompanies, setSelectedRealmId } = useAppStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadCompanies = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.integrations.qboCompanies()
      setCompanies(data)
      if (!selectedRealmId && data.length > 0) {
        setSelectedRealmId(data[0].realm_id)
      }
    } catch {
      setError('Could not load companies. Check your API connection.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadCompanies() }, [])

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
            <button
              onClick={loadCompanies}
              disabled={loading}
              className="flex items-center gap-1.5 text-[11px] text-surface-500 hover:text-surface-700 transition-colors"
            >
              <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2">
              <AlertCircle size={13} className="text-red-500 shrink-0" />
              <p className="text-xs text-red-700">{error}</p>
            </div>
          )}

          {loading && companies.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-surface-400 text-sm">
              <RefreshCw size={14} className="animate-spin mr-2" /> Loading companies...
            </div>
          ) : companies.length > 0 ? (
            <div className="space-y-2">
              <p className="text-[11px] text-surface-500 font-medium uppercase tracking-wide">
                {companies.length} {companies.length === 1 ? 'Company' : 'Companies'} Connected — click to set active
              </p>
              {companies.map(c => (
                <CompanyCard
                  key={c.realm_id}
                  company={c}
                  isSelected={c.realm_id === selectedRealmId}
                  onSelect={() => setSelectedRealmId(c.realm_id)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-surface-200 bg-surface-50 p-6 text-center space-y-3">
              <div className="text-4xl">📊</div>
              <div>
                <p className="text-sm font-semibold text-surface-900">Connect QuickBooks Online</p>
                <p className="text-xs text-surface-500 mt-1 max-w-sm mx-auto">
                  Link your QBO account to enable live auditing, transaction coding, and financial reporting.
                </p>
              </div>
              <button className="btn-primary inline-flex">
                <ExternalLink size={14} /> {t('common.connect')} QuickBooks
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
