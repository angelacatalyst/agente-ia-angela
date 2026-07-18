/**
 * Zustand store — chat conversation state.
 */
import { create } from 'zustand'
import type { AgentModule } from '@/lib/api'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  module?: AgentModule
  tool_calls?: string[]
  timestamp: Date
  isStreaming?: boolean
}

interface ChatState {
  messages: Message[]
  activeModule: AgentModule
  conversationId: string | null
  qboRealmId: string | null
  isStreaming: boolean
  streamingContent: string

  setModule: (module: AgentModule) => void
  setRealmId: (id: string | null) => void
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => string
  updateMessage: (id: string, updates: Partial<Message>) => void
  setStreaming: (v: boolean) => void
  appendStreamChunk: (id: string, chunk: string) => void
  clearConversation: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  activeModule: 'orchestrator',
  conversationId: null,
  qboRealmId: null,
  isStreaming: false,
  streamingContent: '',

  setModule: (module) => set({ activeModule: module }),
  setRealmId: (id) => set({ qboRealmId: id }),

  addMessage: (msg) => {
    const id = crypto.randomUUID()
    set((s) => ({
      messages: [...s.messages, { ...msg, id, timestamp: new Date() }],
    }))
    return id
  },

  updateMessage: (id, updates) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    })),

  setStreaming: (v) => set({ isStreaming: v, streamingContent: v ? '' : '' }),

  appendStreamChunk: (id, chunk) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + chunk } : m,
      ),
    })),

  clearConversation: () =>
    set({ messages: [], conversationId: null, isStreaming: false }),
}))
