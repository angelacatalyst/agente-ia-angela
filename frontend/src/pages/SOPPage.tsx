import { useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAppStore } from '@/stores/appStore'
import { apiClient } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  FileText, Loader2, Download, CheckCircle2, AlertCircle,
  Sparkles, BookOpen, ChevronDown,
} from 'lucide-react'

const QUICK_TOPICS = [
  'Bank Reconciliation in QuickBooks Online',
  'Accounts Payable — Entering and Paying Bills',
  'Accounts Receivable — Creating and Sending Invoices',
  'Month-End Close Process',
  'Payroll Processing and Journal Entry',
  'Chart of Accounts Setup and Maintenance',
  'Vendor Onboarding and 1099 Preparation',
  'Sales Tax Filing and Remittance',
]

export function SOPPage() {
  const { selectedRealmId, companies } = useAppStore()
  const companyName = companies.find(c => c.realm_id === selectedRealmId)?.company_name ?? ''

  const [topic, setTopic] = useState('')
  const [createdBy, setCreatedBy] = useState('Angela – The Profit Catalyst')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [showQuick, setShowQuick] = useState(false)

  const handleGenerate = async () => {
    if (!topic.trim()) return
    setLoading(true)
    setError(null)
    setDone(false)

    try {
      const resp = await apiClient.post(
        '/sops/generate',
        null,
        {
          params: {
            topic: topic.trim(),
            company_name: companyName,
            created_by: createdBy,
          },
          responseType: 'blob',
        },
      )

      // Trigger download
      const url = window.URL.createObjectURL(new Blob([resp.data]))
      const link = document.createElement('a')
      link.href = url
      const safeName = topic.trim().replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 50)
      link.download = `SOP_${safeName}.docx`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      setDone(true)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error generating SOP'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={FileText}
        title="SOP Generator"
        subtitle="Generate Standard Operating Procedures using the TPC template"
        badge="AI"
      />

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto space-y-5">

          {/* Main card */}
          <div className="card p-6 space-y-5">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-primary-500" />
              <h2 className="text-sm font-semibold text-surface-900">Generate a New SOP</h2>
            </div>
            <p className="text-xs text-surface-500 -mt-2">
              Claude escribe el contenido completo y lo descarga en el formato de The Profit Catalyst.
            </p>

            {/* Topic input */}
            <div>
              <label className="block text-xs font-medium text-surface-700 mb-1.5">
                Proceso / Tema del SOP <span className="text-red-400">*</span>
              </label>
              <textarea
                rows={3}
                className="input resize-none"
                placeholder="Ej: Bank Reconciliation in QuickBooks Online, o Cómo crear facturas de clientes en QBO…"
                value={topic}
                onChange={e => { setTopic(e.target.value); setDone(false) }}
              />
            </div>

            {/* Quick topics toggle */}
            <div>
              <button
                onClick={() => setShowQuick(v => !v)}
                className="flex items-center gap-1.5 text-xs text-primary-600 hover:text-primary-700 font-medium"
              >
                <BookOpen size={12} />
                Temas frecuentes
                <ChevronDown size={11} className={cn('transition-transform', showQuick && 'rotate-180')} />
              </button>
              {showQuick && (
                <div className="mt-2 grid grid-cols-1 gap-1.5">
                  {QUICK_TOPICS.map(t => (
                    <button
                      key={t}
                      onClick={() => { setTopic(t); setShowQuick(false); setDone(false) }}
                      className={cn(
                        'text-left rounded-lg border px-3 py-2 text-xs transition-all',
                        'hover:border-primary-300 hover:bg-primary-50 hover:text-primary-700',
                        topic === t
                          ? 'border-primary-400 bg-primary-50 text-primary-700 font-medium'
                          : 'border-surface-200 text-surface-600',
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Created by */}
            <div>
              <label className="block text-xs font-medium text-surface-700 mb-1.5">
                Creado por
              </label>
              <input
                className="input"
                value={createdBy}
                onChange={e => setCreatedBy(e.target.value)}
                placeholder="Tu nombre o firma"
              />
            </div>

            {/* Company context (read-only info) */}
            {companyName && (
              <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 text-xs text-blue-700">
                <span className="font-medium">Contexto de empresa:</span> {companyName}
                <span className="text-blue-500 ml-1">— Claude lo incluirá en el SOP si aplica.</span>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3">
                <AlertCircle size={14} className="text-red-500 shrink-0 mt-0.5" />
                <p className="text-xs text-red-700">{error}</p>
              </div>
            )}

            {/* Success */}
            {done && !loading && (
              <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3">
                <CheckCircle2 size={14} className="text-emerald-600" />
                <p className="text-xs text-emerald-700 font-medium">
                  ¡SOP generado y descargado! Revísalo en tu carpeta de Descargas.
                </p>
              </div>
            )}

            {/* Button */}
            <button
              onClick={handleGenerate}
              disabled={loading || !topic.trim()}
              className="btn-primary w-full justify-center"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Generando SOP con IA… (30–60 seg)
                </>
              ) : (
                <>
                  <Download size={14} />
                  Generar y Descargar SOP (.docx)
                </>
              )}
            </button>
          </div>

          {/* Info card */}
          <div className="card p-5 space-y-3">
            <h3 className="text-xs font-semibold text-surface-800 flex items-center gap-2">
              <FileText size={13} className="text-primary-500" />
              ¿Qué incluye el SOP generado?
            </h3>
            <div className="grid grid-cols-2 gap-2 text-xs text-surface-600">
              {[
                ['📋', 'Document Details', 'Autor, fecha, versión'],
                ['🎯', 'Purpose', 'Por qué existe este proceso'],
                ['🔍', 'Scope', 'Quién lo usa, frecuencia, herramientas'],
                ['📖', 'Key Terminology', 'Glosario de términos clave'],
                ['🗺️', 'Procedure Overview', 'Tabla resumen de pasos'],
                ['📝', 'Procedure Details', 'Pasos detallados con navegación QBO'],
                ['✅', 'Quality Control', 'Problemas comunes y soluciones'],
                ['🗄️', 'Archiving', 'Cómo guardar los registros'],
                ['✍️', 'Approval', 'Firma y fecha de aprobación'],
                ['📎', 'Appendices', 'Recursos adicionales'],
              ].map(([icon, title, desc]) => (
                <div key={title} className="flex items-start gap-2 p-2 rounded-lg bg-surface-50 border border-surface-100">
                  <span className="text-base leading-none mt-0.5">{icon}</span>
                  <div>
                    <p className="font-medium text-surface-700 text-[11px]">{title}</p>
                    <p className="text-[10px] text-surface-400">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-surface-400 pt-1 border-t border-surface-100">
              El archivo descargado es un .docx editable — puedes modificarlo en Word o Google Docs antes de compartirlo.
            </p>
          </div>

        </div>
      </div>
    </div>
  )
}
