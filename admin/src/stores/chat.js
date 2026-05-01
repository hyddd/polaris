import { defineStore } from 'pinia'
import { streamSSE, get } from '../api.js'

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [],
    allMessages: [],
    loading: false,
    toolSteps: [],
    sessionId: null,
  }),
  actions: {
    async loadSession(sid) {
      this.messages = []
      this.sessionId = sid
      this.allMessages = []
      try {
        const data = await get(`/sessions/${sid}`)
        if (data.messages) {
          this.allMessages = data.messages.filter(m => m.type === 'human' || m.type === 'ai')
          // Load last 50 messages
          const recent = this.allMessages.slice(-50)
          for (const m of recent) {
            this.messages.push({
              role: m.type === 'human' ? 'user' : 'assistant',
              content: m.content,
            })
          }
        }
      } catch (e) {
        // Ignore - session might be new
      }
    },
    loadMore() {
      const currentCount = this.messages.length
      if (currentCount >= this.allMessages.length) return false
      const start = Math.max(0, this.allMessages.length - currentCount - 50)
      const end = this.allMessages.length - currentCount
      const older = this.allMessages.slice(start, end)
      for (const m of older.reverse()) {
        this.messages.unshift({
          role: m.type === 'human' ? 'user' : 'assistant',
          content: m.content,
        })
      }
      return true
    },
    clearMessages() {
      this.messages = []
      this.toolSteps = []
    },
    async sendMessage(text) {
      this.messages.push({ role: 'user', content: text })
      this.loading = true
      this.toolSteps = []

      let thinking = ''
      let response = ''
      let hasToolCalls = false

      try {
        await streamSSE(
          '/chat/stream',
          { message: text, channel: 'admin' },
          (token) => {
            if (hasToolCalls) {
              response += token.token || ''
            } else {
              thinking += token.token || ''
            }
            this._updateLastAssistant(thinking || response, hasToolCalls)
          },
          (eventType, data) => {
            if (eventType === 'message') {
              response = data.content || ''
            } else if (eventType === 'tool_call') {
              hasToolCalls = true
              if (thinking.trim()) {
                this.toolSteps.push({ type: 'thought', content: thinking.trim() })
              }
              this.toolSteps.push({
                type: 'tool',
                name: data.tool,
                args: data.args,
                call_id: data.call_id,
                result: '执行中...',
              })
              thinking = ''
            } else if (eventType === 'tool_result') {
              const step = this.toolSteps.find(s => s.call_id === data.call_id)
              if (step) step.result = data.result
            } else if (eventType === 'done') {
              // done
            } else if (eventType === 'error') {
              response = `错误: ${data.error}`
            }
            this._updateLastAssistant(response || thinking, hasToolCalls)
          }
        )
      } catch (e) {
        response = `连接失败: ${e.message}`
      }

      // Mark pending message as complete, or create final message
      const pending = this.messages.find(m => m.role === 'assistant' && m.pending)
      if (pending) {
        pending.content = response || thinking
        pending.tools = [...this.toolSteps]
        delete pending.pending
      } else {
        this.messages.push({ role: 'assistant', content: response || thinking, tools: [...this.toolSteps] })
      }
      this.loading = false
      this.toolSteps = []
    },
    _updateLastAssistant(content, hasToolCalls) {
      const pending = this.messages.find(m => m.role === 'assistant' && m.pending)
      if (pending) {
        pending.content = content
      } else {
        this.messages.push({ role: 'assistant', content, pending: true })
      }
    },
  },
})
