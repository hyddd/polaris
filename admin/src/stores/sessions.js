import { defineStore } from 'pinia'
import { get, post, del } from '../api.js'

export const useSessionsStore = defineStore('sessions', {
  state: () => ({
    sessions: [],
    activeId: '',
  }),
  actions: {
    async fetch() {
      const data = await get('/sessions')
      this.sessions = data.sessions || []
      this.activeId = data.active_session_id || ''
    },
    async create(name) {
      await post('/sessions', { name })
      await this.fetch()
    },
    async switchTo(sid) {
      await post(`/sessions/${sid}/activate`)
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
