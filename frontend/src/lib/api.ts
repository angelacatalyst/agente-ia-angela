/**
 * API client — axios instance + typed endpoint wrappers.
 */
import axios from 'axios'

const API_KEY = import.meta.env.VITE_API_KEY || ''

export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json',
  },
})

// ── Types ────────────────────────────────────────────────────────────────────

export type AgentModule =
  | 'orchestrator'
  | 'qbo_auditor'
  | 'transaction_coder'
  | 'grant_compliance'
  | 'payment_request'
  | 'vendor_onboarding'
  | 'sop_builder'
  | 'eod_report'
  | 'controller'
  | 'bank_reconciliation'
  | 'payroll_allocation'

export interface ChatRequest {
  message: string
  module?: AgentModule
  conversation_id?: string
  qbo_realm_id?: string
  context?: Record<string, unknown>
}

export interface ChatResponse {
  conversation_id: string
  module: AgentModule
  content: string
  tool_calls_made: string[]
  created_at: string
}

export interface HealthResponse {
  status: string
  version: string
  environment: string
  services: Record<string, string>
}

// ── SSE Streaming ─────────────────────────────────────────────────────────────

export interface StreamEvent {
  type: 'routing' | 'token' | 'done' | 'error'
  content?: string
  module?: AgentModule
  detail?: string
}

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
    },
    body: JSON.stringify(request),
    signal,
  })

  if (!response.ok) {
    throw new Error(`Stream error: ${response.status}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event: StreamEvent = JSON.parse(line.slice(6))
          yield event
          if (event.type === 'done' || event.type === 'error') return
        } catch {
          // malformed chunk, ignore
        }
      }
    }
  }
}

// ── Standard API calls ────────────────────────────────────────────────────────

export const api = {
  health: () => apiClient.get<HealthResponse>('/health').then(r => r.data),

  chat: (req: ChatRequest) =>
    apiClient.post<ChatResponse>('/chat', req).then(r => r.data),

  audit: {
    run: (realmId: string, asOfDate?: string) =>
      apiClient.post('/audit/run', { realm_id: realmId, as_of_date: asOfDate }).then(r => r.data),
    ask: (realmId: string, question: string) =>
      apiClient.post('/audit/ask', null, { params: { realm_id: realmId, question } }).then(r => r.data),
  },

  transactions: {
    code: (payload: unknown) =>
      apiClient.post('/transactions/code', payload).then(r => r.data),
    codeFile: (file: File, orgType: string, grants: string, programs: string) => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('organization_type', orgType)
      fd.append('active_grants', grants)
      fd.append('active_programs', programs)
      return apiClient.post('/transactions/code/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then(r => r.data)
    },
  },

  grants: {
    audit: (payload: unknown) =>
      apiClient.post('/grants/audit', payload).then(r => r.data),
  },

  payments: {
    review: (payload: unknown) =>
      apiClient.post('/payments/review', payload).then(r => r.data),
    reviewInvoice: (file: File, approver?: string) => {
      const fd = new FormData()
      fd.append('file', file)
      if (approver) fd.append('approver', approver)
      return apiClient.post('/payments/review/invoice', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then(r => r.data)
    },
  },

  vendors: {
    onboard: (payload: unknown) =>
      apiClient.post('/vendors/onboard', payload).then(r => r.data),
  },

  sops: {
    build: (payload: unknown) =>
      apiClient.post('/sops/build', payload).then(r => r.data),
    quick: (description: string) =>
      apiClient.post('/sops/build/quick', null, { params: { description } }).then(r => r.data),
  },

  eod: {
    generate: (rawNotes: string, date?: string) =>
      apiClient.post('/eod/generate', { raw_notes: rawNotes, date }).then(r => r.data),
  },

  controller: {
    briefing: (payload: unknown) =>
      apiClient.post('/controller/briefing', payload).then(r => r.data),
    monthEnd: (realmId: string, month: string, year: string) =>
      apiClient.post('/controller/month-end', null, {
        params: { realm_id: realmId, month, year },
      }).then(r => r.data),
  },

  qboData: {
    dashboard: (realmId: string) =>
      apiClient.get<QBODashboard>('/qbo/data/dashboard', { params: { realm_id: realmId } }).then(r => r.data),
    vendors: (realmId: string) =>
      apiClient.get<{ vendors: QBOVendor[]; total: number }>('/qbo/data/vendors', { params: { realm_id: realmId } }).then(r => r.data),
    bills: (realmId: string, unpaidOnly = true) =>
      apiClient.get<{ bills: QBOBill[]; total: number }>('/qbo/data/bills', { params: { realm_id: realmId, unpaid_only: unpaidOnly } }).then(r => r.data),
    transactions: (realmId: string) =>
      apiClient.get<{ transactions: QBOTransaction[]; total: number }>('/qbo/data/transactions', { params: { realm_id: realmId } }).then(r => r.data),
  },

  integrations: {
    qboStatus: (realmId: string) =>
      apiClient.get('/integrations/qbo/status', { params: { realm_id: realmId } }).then(r => r.data),
    qboAuthorize: (userId: string) =>
      apiClient.get('/integrations/qbo/authorize', { params: { user_id: userId } }).then(r => r.data),
    qboDisconnect: (realmId: string) =>
      apiClient.delete('/integrations/qbo/disconnect', { params: { realm_id: realmId } }).then(r => r.data),
    qboCompanies: () =>
      apiClient.get<QBOCompany[]>('/integrations/qbo/companies').then(r => r.data),
  },
}

export interface QBOCompany {
  realm_id: string
  company_name: string
  connected: boolean
  token_expired: boolean
  expires_at: string
}

// ── QBO Data types ────────────────────────────────────────────────────────────

export interface QBOKpi {
  label: string
  value: string
  raw: number | null
  source: string
}

export interface QBOAlert {
  level: 'high' | 'medium' | 'low'
  text: string
}

export interface QBODashboard {
  kpis: QBOKpi[]
  alerts: QBOAlert[]
  priorities: string[]
  errors: string[]
  fetched_at: string
}

export interface QBOVendor {
  id: string
  name: string
  email: string
  phone: string
  balance: number
  balance_formatted: string
  active: boolean
  vendor_1099: boolean
  currency: string
}

export interface QBOBill {
  id: string
  vendor: string
  amount: number
  amount_formatted: string
  balance: number
  balance_formatted: string
  due_date: string
  txn_date: string
  status: 'pending' | 'overdue'
  doc_number: string
}

export interface QBOTransaction {
  date: string
  payee: string
  amount: string
  type: string
  status: string
  doc_number: string
}
