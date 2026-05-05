<template>
  <div class="page">
    <div class="page-header">
      <h1>提醒管理</h1>
      <button class="btn btn-primary" @click="showCreate = true">
        <el-icon><Plus /></el-icon> 新建提醒
      </button>
    </div>

    <!-- Create Form Modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h3>新建提醒</h3>
        <div class="form-group">
          <label>标题</label>
          <input v-model="form.title" placeholder="提醒标题" class="form-input" />
        </div>
        <div class="form-group">
          <label>描述</label>
          <textarea v-model="form.description" placeholder="提醒描述（可选）" class="form-textarea" />
        </div>
        <div class="form-group">
          <label>触发时间</label>
          <input v-model="form.trigger_time" type="datetime-local" class="form-input" />
        </div>
        <div class="form-group">
          <label>重复规则</label>
          <select v-model="form.repeat_rule" class="form-input">
            <option value="none">不重复</option>
            <option value="daily">每天</option>
            <option value="weekly">每周</option>
            <option value="monthly">每月</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createReminder" :disabled="!form.title || !form.trigger_time">创建</button>
        </div>
      </div>
    </div>

    <!-- Reminders List -->
    <div class="data-content">
      <div v-if="loading" class="empty">加载中...</div>
      <div v-else-if="!reminders.length" class="empty">暂无提醒</div>
      <div v-else class="reminder-list">
        <div v-for="r in reminders" :key="r.id" class="reminder-card">
          <div class="reminder-main">
            <div class="reminder-title">{{ r.title }}</div>
            <div v-if="r.description" class="reminder-desc">{{ r.description }}</div>
            <div class="reminder-meta">
              <span class="reminder-time">
                <el-icon><Clock /></el-icon>
                {{ formatTime(r.trigger_time) }}
              </span>
              <span :class="['badge', `repeat-${r.repeat_rule}`]">{{ repeatLabel(r.repeat_rule) }}</span>
              <span :class="['badge', `status-${r.status}`]">{{ statusLabel(r.status) }}</span>
            </div>
          </div>
          <div class="reminder-actions">
            <button
              v-if="r.status === 'active'"
              class="btn btn-small"
              @click="pauseReminder(r.id)"
              title="暂停"
            >
              <el-icon><VideoPause /></el-icon>
            </button>
            <button
              v-if="r.status === 'paused'"
              class="btn btn-small"
              @click="resumeReminder(r.id)"
              title="恢复"
            >
              <el-icon><VideoPlay /></el-icon>
            </button>
            <button class="btn btn-small btn-danger" @click="deleteReminder(r.id)" title="删除">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { get, post, del } from '../api.js'

const reminders = ref([])
const loading = ref(true)
const showCreate = ref(false)
const form = ref({
  title: '',
  description: '',
  trigger_time: '',
  repeat_rule: 'none',
})

onMounted(fetchReminders)

async function fetchReminders() {
  loading.value = true
  try {
    const data = await get('/api/reminders')
    reminders.value = data.items || []
  } catch (e) {
    ElMessage.error('加载提醒列表失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function createReminder() {
  if (!form.value.title || !form.value.trigger_time) return
  try {
    await post('/api/reminders', {
      title: form.value.title,
      description: form.value.description,
      trigger_time: new Date(form.value.trigger_time).toISOString(),
      repeat_rule: form.value.repeat_rule,
    })
    showCreate.value = false
    form.value = { title: '', description: '', trigger_time: '', repeat_rule: 'none' }
    await fetchReminders()
    ElMessage.success('提醒已创建')
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  }
}

async function deleteReminder(id) {
  if (!confirm('确认删除此提醒？')) return
  try {
    await del(`/api/reminders/${id}`)
    await fetchReminders()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

async function pauseReminder(id) {
  try {
    await post(`/api/reminders/${id}/pause`)
    await fetchReminders()
    ElMessage.success('已暂停')
  } catch (e) {
    ElMessage.error('暂停失败: ' + e.message)
  }
}

async function resumeReminder(id) {
  try {
    await post(`/api/reminders/${id}/resume`)
    await fetchReminders()
    ElMessage.success('已恢复')
  } catch (e) {
    ElMessage.error('恢复失败: ' + e.message)
  }
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function repeatLabel(rule) {
  const map = { none: '不重复', daily: '每天', weekly: '每周', monthly: '每月' }
  return map[rule] || rule
}

function statusLabel(status) {
  const map = { active: '活跃', paused: '已暂停', cancelled: '已取消' }
  return map[status] || status
}
</script>

<style scoped>
.page { max-width: 768px; margin: 0 auto; padding: 32px 24px; height: 100vh; overflow-y: auto; }
.page-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;
}
.page-header h1 { font-size: 24px; font-weight: 400; }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.modal {
  background: var(--bg-secondary); border: 1px solid var(--border-primary);
  border-radius: 12px; padding: 24px; width: 400px; max-width: 90vw;
}
.modal h3 { font-size: 18px; font-weight: 500; margin-bottom: 16px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.form-input, .form-textarea {
  width: 100%; padding: 10px 12px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: var(--bg-tertiary); color: var(--text-primary); font-size: 14px;
}
.form-textarea { min-height: 60px; resize: vertical; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }

/* Reminder List */
.reminder-list { display: flex; flex-direction: column; gap: 8px; }
.reminder-card {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 14px 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
  border-radius: 10px;
}
.reminder-main { flex: 1; }
.reminder-title { font-size: 15px; margin-bottom: 4px; }
.reminder-desc { font-size: 13px; color: var(--text-tertiary); margin-bottom: 8px; }
.reminder-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.reminder-time {
  display: flex; align-items: center; gap: 4px;
  font-size: 13px; color: var(--text-tertiary);
}
.reminder-actions { display: flex; gap: 6px; margin-left: 12px; }

/* Badges */
.badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  font-weight: 500;
}
.repeat-none { background: #3f3f46; color: #a1a1aa; }
.repeat-daily { background: #1e3a5f; color: #93c5fd; }
.repeat-weekly { background: #2d1b69; color: #c4b5fd; }
.repeat-monthly { background: #14532d; color: #86efac; }
.status-active { background: #14532d; color: #86efac; }
.status-paused { background: #78350f; color: #fcd34d; }
.status-cancelled { background: #3f3f46; color: #a1a1aa; }

/* Empty */
.empty { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 14px; }

/* Button */
.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger { color: var(--danger); border-color: var(--danger-bg); }
.btn-danger:hover { background: var(--danger-bg); }
.btn-small { padding: 6px 12px; font-size: 12px; }
</style>
