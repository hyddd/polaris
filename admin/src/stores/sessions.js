import { defineStore } from 'pinia'
import { get, post, del } from '../api.js'
import { ElMessage } from 'element-plus'

export const useSessionsStore = defineStore('sessions', {
  state: () => ({
    sessions: [],
    activeId: '',
  }),
  actions: {
    async fetch() {
      const data = await get('/sessions?channel=admin')
      this.sessions = data.sessions || []
      this.activeId = data.active_session_id || ''
    },
    async create(name) {
      try {
        await post('/sessions', { name, source_channel: 'admin' })
        await this.fetch()
      } catch (e) {
        ElMessage.error(e.message)
        throw e
      }
    },
    async switchTo(sid) {
      await post(`/sessions/${sid}/activate?channel=admin`)
      await this.fetch()
    },
    async remove(sid) {
      await del(`/sessions/${sid}`)
      await this.fetch()
    },
    async rename(sid, name) {
      await post('/chat', { message: `/rename ${name}`, channel: 'admin' })
      await this.fetch()
    },
  },
})
