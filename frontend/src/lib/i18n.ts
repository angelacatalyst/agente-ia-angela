/**
 * Simple i18n — bilingual support ES / EN.
 * Usage:
 *   const { t, lang, setLang } = useI18n()
 *   t('chat.title')
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Lang = 'en' | 'es'

const translations = {
  en: {
    // Nav
    'nav.chat':         'AI Chat',
    'nav.controller':   'Controller',
    'nav.audit':        'QBO Auditor',
    'nav.transactions': 'Transactions',
    'nav.grants':       'Grants',
    'nav.payments':     'Payments',
    'nav.vendors':      'Vendors',
    'nav.sops':         'SOPs',
    'nav.eod':          'EOD Reports',
    'nav.settings':     'Settings',

    // App
    'app.name':    'Finance Ops',
    'app.tagline': 'AI Manager',
    'app.powered': 'Powered by Claude + LangGraph',

    // Chat
    'chat.title':       'Finance Operations Chat',
    'chat.placeholder': 'Ask anything about accounting, QBO, grants, transactions…',
    'chat.empty.title': 'Finance Operations AI',
    'chat.empty.desc':  'Your AI-powered accounting manager. Ask anything about QBO, transactions, grants, or compliance.',
    'chat.clear':       'Clear conversation',
    'chat.module':      'Module',
    'chat.hint':        'Enter to send · Shift+Enter for new line',

    // Quick prompts
    'qp.audit':      'Run QBO Audit',
    'qp.audit.desc': 'Run a complete accounting audit of my QBO file and identify all high-risk issues.',
    'qp.code':       'Code Transactions',
    'qp.code.desc':  'I need to code my latest bank transactions. Please guide me through the process.',
    'qp.grants':     'Grant Compliance',
    'qp.grants.desc':'Review all active grants for compliance issues and identify any at-risk spending.',
    'qp.morning':    'Morning Briefing',
    'qp.morning.desc':"Generate my controller morning briefing with today's priorities and financial risks.",
    'qp.eod':        'EOD Report',
    'qp.eod.desc':   'Help me create my end-of-day report.',
    'qp.sop':        'New SOP',
    'qp.sop.desc':   'I need to document a new accounting process. Help me create a standard SOP.',

    // Modules
    'module.orchestrator':     '⚡ Auto-Route',
    'module.qbo_auditor':      '🔍 QBO Auditor',
    'module.transaction_coder':'🏷️ Transaction Coder',
    'module.grant_compliance': '🛡️ Grant Compliance',
    'module.payment_request':  '💳 Payment Requests',
    'module.vendor_onboarding':'👤 Vendor Onboarding',
    'module.sop_builder':      '📖 SOP Builder',
    'module.eod_report':       '📋 EOD Report',
    'module.controller':       '📊 Controller',

    // Pages
    'page.controller.title':    'Fractional Controller',
    'page.controller.subtitle': 'Strategic financial oversight and morning briefings',
    'page.audit.title':         'QBO Auditor',
    'page.audit.subtitle':      'Automated accounting audit and risk detection',
    'page.transactions.title':  'Transaction Coder',
    'page.transactions.subtitle':'AI-assisted transaction coding and classification',
    'page.grants.title':        'Grant Compliance',
    'page.grants.subtitle':     'Grant tracking and compliance monitoring',
    'page.payments.title':      'Payment Requests',
    'page.payments.subtitle':   'Payment request generation and approval workflow',
    'page.vendors.title':       'Vendor Onboarding',
    'page.vendors.subtitle':    'Vendor setup, W-9 collection, and 1099 tracking',
    'page.sops.title':          'SOP Builder',
    'page.sops.subtitle':       'Document and manage accounting standard procedures',
    'page.eod.title':           'EOD Reports',
    'page.eod.subtitle':        'End-of-day financial summaries and reconciliation',
    'page.settings.title':      'Settings',
    'page.settings.subtitle':   'API keys, QuickBooks connection, and preferences',

    // Common
    'common.loading':    'Loading…',
    'common.error':      'Something went wrong',
    'common.save':       'Save',
    'common.cancel':     'Cancel',
    'common.export':     'Export',
    'common.upload':     'Upload File',
    'common.generate':   'Generate',
    'common.connect':    'Connect',
    'common.connected':  'Connected',
    'common.disconnect': 'Disconnect',
    'common.beta':       'Beta',
    'common.new':        'New',

    // Settings
    'settings.api_keys':    'API Keys',
    'settings.qbo':         'QuickBooks Online',
    'settings.language':    'Language',
    'settings.en':          'English',
    'settings.es':          'Español',
  },

  es: {
    // Nav
    'nav.chat':         'Chat IA',
    'nav.controller':   'Controller',
    'nav.audit':        'Auditor QBO',
    'nav.transactions': 'Transacciones',
    'nav.grants':       'Subvenciones',
    'nav.payments':     'Pagos',
    'nav.vendors':      'Proveedores',
    'nav.sops':         'SOPs',
    'nav.eod':          'Reportes EOD',
    'nav.settings':     'Configuración',

    // App
    'app.name':    'Finance Ops',
    'app.tagline': 'Agente IA',
    'app.powered': 'Powered by Claude + LangGraph',

    // Chat
    'chat.title':       'Chat de Operaciones Financieras',
    'chat.placeholder': 'Pregunta sobre QBO, transacciones, subvenciones, cumplimiento…',
    'chat.empty.title': 'Agente IA Financiero',
    'chat.empty.desc':  'Tu agente de contabilidad con IA. Pregunta sobre QBO, transacciones, subvenciones o cumplimiento.',
    'chat.clear':       'Limpiar conversación',
    'chat.module':      'Módulo',
    'chat.hint':        'Enter para enviar · Shift+Enter para nueva línea',

    // Quick prompts
    'qp.audit':       'Auditoría QBO',
    'qp.audit.desc':  'Ejecuta una auditoría completa de mi archivo QBO e identifica todos los riesgos.',
    'qp.code':        'Codificar Transacciones',
    'qp.code.desc':   'Necesito codificar mis últimas transacciones bancarias. Guíame en el proceso.',
    'qp.grants':      'Cumplimiento de Grants',
    'qp.grants.desc': 'Revisa todos los grants activos para detectar problemas de cumplimiento.',
    'qp.morning':     'Briefing Matutino',
    'qp.morning.desc':'Genera mi briefing matutino de controller con prioridades y riesgos financieros.',
    'qp.eod':         'Reporte EOD',
    'qp.eod.desc':    'Ayúdame a crear mi reporte de fin de día.',
    'qp.sop':         'Nuevo SOP',
    'qp.sop.desc':    'Necesito documentar un nuevo proceso contable. Ayúdame a crear un SOP estándar.',

    // Modules
    'module.orchestrator':     '⚡ Auto-Ruta',
    'module.qbo_auditor':      '🔍 Auditor QBO',
    'module.transaction_coder':'🏷️ Coder Transacciones',
    'module.grant_compliance': '🛡️ Cumplimiento Grants',
    'module.payment_request':  '💳 Solicitudes de Pago',
    'module.vendor_onboarding':'👤 Alta de Proveedores',
    'module.sop_builder':      '📖 Constructor de SOPs',
    'module.eod_report':       '📋 Reporte EOD',
    'module.controller':       '📊 Controller',

    // Pages
    'page.controller.title':    'Controller Fraccionado',
    'page.controller.subtitle': 'Supervisión financiera estratégica y briefings matutinos',
    'page.audit.title':         'Auditor QBO',
    'page.audit.subtitle':      'Auditoría contable automatizada y detección de riesgos',
    'page.transactions.title':  'Codificador de Transacciones',
    'page.transactions.subtitle':'Codificación y clasificación de transacciones asistida por IA',
    'page.grants.title':        'Cumplimiento de Subvenciones',
    'page.grants.subtitle':     'Seguimiento de grants y monitoreo de cumplimiento',
    'page.payments.title':      'Solicitudes de Pago',
    'page.payments.subtitle':   'Generación de solicitudes de pago y flujo de aprobación',
    'page.vendors.title':       'Alta de Proveedores',
    'page.vendors.subtitle':    'Configuración de proveedores, W-9 y seguimiento 1099',
    'page.sops.title':          'Constructor de SOPs',
    'page.sops.subtitle':       'Documenta y gestiona procedimientos contables estándar',
    'page.eod.title':           'Reportes EOD',
    'page.eod.subtitle':        'Resúmenes financieros de fin de día y conciliación',
    'page.settings.title':      'Configuración',
    'page.settings.subtitle':   'Claves API, conexión QuickBooks y preferencias',

    // Common
    'common.loading':    'Cargando…',
    'common.error':      'Algo salió mal',
    'common.save':       'Guardar',
    'common.cancel':     'Cancelar',
    'common.export':     'Exportar',
    'common.upload':     'Subir Archivo',
    'common.generate':   'Generar',
    'common.connect':    'Conectar',
    'common.connected':  'Conectado',
    'common.disconnect': 'Desconectar',
    'common.beta':       'Beta',
    'common.new':        'Nuevo',

    // Settings
    'settings.api_keys':    'Claves de API',
    'settings.qbo':         'QuickBooks Online',
    'settings.language':    'Idioma',
    'settings.en':          'English',
    'settings.es':          'Español',
  },
} as const

type TranslationKey = keyof typeof translations['en']

interface I18nState {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: TranslationKey) => string
}

export const useI18n = create<I18nState>()(
  persist(
    (set, get) => ({
      lang: 'en',
      setLang: (lang) => set({ lang }),
      t: (key) => {
        const { lang } = get()
        return (translations[lang] as Record<string, string>)[key]
          ?? (translations['en'] as Record<string, string>)[key]
          ?? key
      },
    }),
    { name: 'finance-ops-lang' },
  ),
)
