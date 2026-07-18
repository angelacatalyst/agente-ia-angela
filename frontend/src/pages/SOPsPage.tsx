import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  BookOpen, Loader2, Plus, FileText, Clock,
  ChevronRight, Download, Search,
} from 'lucide-react'

const SOP_TEMPLATES = [
  'Month-End Close Procedure',
  'Accounts Payable Processing',
  'Payroll Processing & Approval',
  'Grant Expenditure Reporting',
  'Bank Reconciliation',
  'Vendor Onboarding Workflow',
  'Travel & Expense Reimbursement',
  'Fixed Asset Management',
]

interface SOPDoc {
  id: string; title: string; version: string; updatedAt: string; status: 'active' | 'draft'
}

const EXISTING_SOPS: SOPDoc[] = [
  { id: '1', title: 'Month-End Close Procedure',  version: 'v2.1', updatedAt: '2024-03-15', status: 'active' },
  { id: '2', title: 'Accounts Payable Processing', version: 'v1.4', updatedAt: '2024-02-28', status: 'active' },
  { id: '3', title: 'Grant Reporting Workflow',    version: 'v1.0', updatedAt: '2024-04-01', status: 'draft'  },
]

export function SOPsPage() {
  const { t } = useI18n()
  const [processName, setProcessName] = useState('')
  const [context, setContext]         = useState('')
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [result, setResult]           = useState<string | null>(null)
  const [search, setSearch]           = useState('')

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Generate a complete SOP document for: ${processName || selectedTemplate}. Context: ${context || 'Standard accounting department'}. Include: Purpose, Scope, Responsible Parties, Step-by-Step Procedure, Controls, and Review Schedule.`,
      module: 'sop_builder',
    }),
    onSuccess: (d) => setResult(d.content),
  })

  const filtered = EXISTING_SOPS.filter(s =>
    s.title.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={BookOpen}
        title={t('page.sops.title')}
        subtitle={t('page.sops.subtitle')}
        badge="AI"
        actions={
          result && (
            <button className="btn-primary text-[13px]">
              <Download size={14} /> Export PDF
            </button>
          )
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="grid grid-cols-3 gap-5">
          {/* Left: library */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-surface-900 mb-3">SOP Library</h2>
            <div className="relative mb-3">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
              <input
                className="input pl-8 text-xs"
                placeholder="Search SOPs…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              {filtered.map(s => (
                <div key={s.id} className="flex items-center gap-2.5 rounded-lg px-3 py-2.5 hover:bg-surface-50 border border-surface-100 hover:border-surface-200 transition-all cursor-pointer group">
                  <FileText size={14} className="text-surface-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-surface-800 truncate">{s.title}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="text-[10px] text-surface-400">{s.version}</span>
                      <span className="text-[10px] text-surface-300">·</span>
                      <Clock size={9} className="text-surface-400" />
                      <span className="text-[10px] text-surface-400">{s.updatedAt}</span>
                    </div>
                  </div>
                  <span className={cn('badge text-[10px]', s.status === 'active' ? 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200' : 'bg-surface-100 text-surface-500')}>
                    {s.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Middle: generator */}
          <div className="card p-5 space-y-4">
            <h2 className="text-sm font-semibold text-surface-900">Generate New SOP</h2>

            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">Process Name</label>
              <input
                className="input"
                placeholder="e.g. Month-End Close"
                value={processName}
                onChange={e => setProcessName(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-surface-600 mb-2">Or Use Template</label>
              <div className="space-y-1">
                {SOP_TEMPLATES.map(t => (
                  <button
                    key={t}
                    onClick={() => setSelectedTemplate(t)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs transition-all',
                      selectedTemplate === t
                        ? 'bg-primary-50 text-primary-700 font-medium ring-1 ring-primary-200'
                        : 'text-surface-600 hover:bg-surface-50',
                    )}
                  >
                    <ChevronRight size={11} />
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">Additional Context</label>
              <textarea
                rows={3}
                className="input resize-none text-xs"
                placeholder="Organization type, specific requirements, tools used…"
                value={context}
                onChange={e => setContext(e.target.value)}
              />
            </div>

            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || (!processName && !selectedTemplate)}
              className="btn-primary w-full justify-center"
            >
              {mutation.isPending
                ? <><Loader2 size={14} className="animate-spin" /> Generating…</>
                : <><Plus size={14} /> Generate SOP</>
              }
            </button>
          </div>

          {/* Right: result */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <FileText size={16} className="text-primary-600" />
              <h2 className="text-sm font-semibold text-surface-900">Generated SOP</h2>
            </div>

            {result ? (
              <div className="text-sm text-surface-800 whitespace-pre-wrap leading-relaxed overflow-y-auto max-h-[calc(100vh-280px)]">
                {result}
              </div>
            ) : (
              <div className="flex h-48 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                <div className="text-center">
                  <BookOpen size={28} className="mx-auto mb-2 text-surface-300" />
                  <p className="text-sm text-surface-400">Your SOP document will appear here</p>
                  <p className="text-xs text-surface-300 mt-1">Includes steps, controls & review schedule</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
