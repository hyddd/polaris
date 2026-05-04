import { defineStore } from 'pinia'
import { streamSSE, get } from '../api.js'

let _msgIdCounter = 0

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
        const data = await get(`/api/sessions/${sid}?channel=admin`)
        if (data.messages) {
          this.allMessages = data.messages.filter(m => m.type === 'human' || m.type === 'ai')
          // Load last 50 messages
          const recent = this.allMessages.slice(-50)
          for (const m of recent) {
            this.messages.push({
              id: m.id || `msg_${++_msgIdCounter}`,
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
          id: m.id || `msg_${++_msgIdCounter}`,
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
      const msgId = `msg_${++_msgIdCounter}`
      this.messages.push({ id: msgId, role: 'user', content: text })
      this.loading = true
      this.toolSteps = []

      await this._streamResponse({ message: text, channel: 'admin' })
    },
    async retryMessage(messageId) {
      // Find the message to retry
      const msg = this.messages.find(m => m.id === messageId)
      if (!msg || msg.role !== 'user') return

      this.loading = true
      this.toolSteps = []

      // Remove all messages after the retried message
      const idx = this.messages.findIndex(m => m.id === messageId)
      if (idx >= 0) {
        this.messages.splice(idx + 1)
      }

      await this._streamResponse({
        message: msg.content,
        channel: 'admin',
        retry_message_id: messageId,
      })
    },
    async editMessage(messageId, newContent) {
      // Find the message to edit
      const msg = this.messages.find(m => m.id === messageId)
      if (!msg || msg.role !== 'user') return

      // Update the message content
      msg.content = newContent

      this.loading = true
      this.toolSteps = []

      // Remove all messages after the edited message
      const idx = this.messages.findIndex(m => m.id === messageId)
      if (idx >= 0) {
        this.messages.splice(idx + 1)
      }

      await this._streamResponse({
        message: newContent,
        channel: 'admin',
        edit_message_id: messageId,
        edit_content: newContent,
      })
    },
    async _streamResponse(data) {
      let thinking = ''
      let response = ''
      let hasToolCalls = false

      try {
        await streamSSE(
          '/api/chat/stream',
          data,
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
        response = e.message
      }

      // Mark pending message as complete, or create final message
      const pending = this.messages.find(m => m.role === 'assistant' && m.pending)
      if (pending) {
        pending.content = response || thinking
        pending.tools = [...this.toolSteps]
        delete pending.pending
      } else {
        this.messages.push({
          id: `msg_${++_msgIdCounter}`,
          role: 'assistant',
          content: response || thinking,
          tools: [...this.toolSteps],
        })
      }
      this.loading = false
      this.toolSteps = []
    },
    _updateLastAssistant(content, hasToolCalls) {
      const pending = this.messages.find(m => m.role === 'assistant' && m.pending)
      if (pending) {
        pending.content = content
      } else {
        this.messages.push({
          id: `msg_${++_msgIdCounter}`,
          role: 'assistant',
          content,
          pending: true,
        })
      }
    },
  },
})
