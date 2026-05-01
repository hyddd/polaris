<template>
  <div class="page">
    <div class="page-header">
      <h1>会话管理</h1>
      <button class="btn btn-primary" @click="showCreate = true">
        <el-icon><Plus /></el-icon> 新建会话
      </button>
    </div>

    <div class="session-list">
      <div
        v-for="s in store.sessions"
        :key="s.session_id"
        :class="['session-card', { active: s.session_id === store.activeId }]"
      >
        <div class="session-info">
          <div class="session-name">
            <span v-if="s.session_id === store.activeId" class="active-badge">当前</span>
            {{ s.name }}
          </div>
          <div class="session-meta">
            {{ s.session_id }} · {{ s.message_count || 0 }} 条消息
          </div>
        </div>
        <div class="session-actions">
          <button v-if="s.session_id !== store.activeId" class="btn btn-small" @click="store.switchTo(s.session_id)">切换</button>
          <button class="btn btn-small" @click="handleRename(s.session_id)">重命名</button>
          <button v-if="store.sessions.length > 1" class="btn btn-small btn-danger" @click="handleDelete(s.session_id)">删除</button>
        </div>
      </div>
    </div>

    <!-- Create dialog -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h3>新建会话</h3>
        <input v-model="newName" placeholder="会话名称" class="dark-input" @keydown.enter="create" />
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="create">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'

const store = useSessionsStore()
const showCreate = ref(false)
const newName = ref('')

onMounted(() => store.fetch())

async function create() {
  if (newName.value.trim()) {
    await store.create(newName.value.trim())
    newName.value = ''
    showCreate.value = false
  }
}

async function handleDelete(sid) {
  if (!confirm('确认删除此会话？')) return
  await store.remove(sid)
}

async function handleRename(sid) {
  const name = prompt('输入新名称')
  if (name) await store.rename(sid, name)
}
</script>

<style scoped>
.page { max-width: 768px; margin: 0 auto; padding: 32px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 400; }

.session-list { display: flex; flex-direction: column; gap: 8px; }
.session-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px; background: #2f2f2f; border: 1px solid #424242; border-radius: 12px;
  transition: border-color 0.2s;
}
.session-card.active { border-color: #6b9eff; }
.session-name { font-size: 15px; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
.active-badge {
  font-size: 11px; background: #1b7c5a; color: #fff; padding: 2px 8px;
  border-radius: 10px;
}
.session-meta { font-size: 13px; color: #8e8e8e; }
.session-actions { display: flex; gap: 8px; }

/* Buttons */
.btn {
  padding: 8px 16px; border: 1px solid #424242; border-radius: 8px;
  background: transparent; color: #ececec; font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.btn:hover { background: #3a3a3a; }
.btn-primary { background: #3b6bed; border-color: #3b6bed; }
.btn-primary:hover { background: #4a7af0; }
.btn-danger { color: #ef4444; border-color: #7f1d1d; }
.btn-danger:hover { background: #7f1d1d; }
.btn-small { padding: 6px 12px; font-size: 12px; }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex;
  align-items: center; justify-content: center; z-index: 100;
}
.modal {
  background: #2f2f2f; border: 1px solid #424242; border-radius: 16px;
  padding: 24px; width: 400px;
}
.modal h3 { margin-bottom: 16px; font-weight: 400; }
.dark-input {
  width: 100%; padding: 10px 14px; background: #1a1a1a; border: 1px solid #424242;
  border-radius: 8px; color: #ececec; font-size: 14px; outline: none;
}
.dark-input:focus { border-color: #6b9eff; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
