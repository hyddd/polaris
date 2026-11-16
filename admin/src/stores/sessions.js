import { defineStore } from 'pinia'
import { get, post, put, del } from '../api.js'
import { ElMessage } from 'element-plus'

export const useSessionsStore = defineStore('sessions', {
  state: () => ({
    sessions: [],
    activeId: '',
  }),
  actions: {
    async fetch() {
      const data = await get('/api/sessions?channel=admin')
      this.sessions = data.sessions || []
      this.activeId = data.active_session_id || ''
    },
    async create(name) {
      try {
        await post('/api/sessions', { name, source_channel: 'admin' })
        await this.fetch()
      } catch (e) {
        ElMessage.error(e.message)
        throw e
      }
    },
    async switchTo(sid) {
      await post(`/api/sessions/${sid}/activate?channel=admin`)
      await this.fetch()
    },
    async remove(sid) {
      await del(`/api/sessions/${sid}`)
      await this.fetch()
    },
    async rename(sid, name) {
      // 按 ID 改名；以前发聊天命令 /rename，改的是当前激活会话而不是 sid
      try {
        await put(`/api/sessions/${sid}`, { name })
        await this.fetch()
      } catch (e) {
        ElMessage.error(e.message)
        throw e
      }
    },
  },
})
