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
import { ElMessageBox, ElMessage } from 'element-plus'
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
  try {
    await ElMessageBox.confirm('此操作不可恢复。', '删除会话', {
      type: 'warning',
      confirmButtonText: '确认删除',
    })
  } catch { return }
  await store.remove(sid)
}

async function handleRename(sid) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新名称', '重命名会话', {
      inputValue: store.sessions.find(s => s.session_id === sid)?.name || sid,
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputValidator: (val) => {
        if (!val || !val.trim()) return '名称不能为空'
        return true
      },
    })
    await store.rename(sid, value.trim())
    ElMessage.success('重命名成功')
  } catch {
    // 用户取消
  }
}
</script>

<style scoped>
.page { max-width: 768px; margin: 0 auto; padding: 32px 24px; height: 100vh; overflow-y: auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 400; }

.session-list { display: flex; flex-direction: column; gap: 8px; }
.session-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 12px;
  transition: border-color 0.2s;
}
.session-card.active { border-color: var(--accent); }
.session-name { font-size: 15px; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
.active-badge {
  font-size: 11px; background: var(--success); color: #fff; padding: 2px 8px;
  border-radius: 10px;
}
.session-meta { font-size: 13px; color: var(--text-tertiary); }
.session-actions { display: flex; gap: 8px; }

/* Buttons */
.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-danger { color: var(--danger); border-color: var(--danger-bg); }
.btn-danger:hover { background: var(--danger-bg); }
.btn-small { padding: 6px 12px; font-size: 12px; }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex;
  align-items: center; justify-content: center; z-index: 100;
}
.modal {
  background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 16px;
  padding: 24px; width: 400px;
}
.modal h3 { margin-bottom: 16px; font-weight: 400; }
.dark-input {
  width: 100%; padding: 10px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-primary);
  border-radius: 8px; color: var(--text-primary); font-size: 14px; outline: none;
}
.dark-input:focus { border-color: var(--accent); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
