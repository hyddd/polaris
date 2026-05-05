<template>
  <div class="page">
    <div class="page-header">
      <h1>日程管理</h1>
      <button class="btn btn-primary btn-small" @click="showCreate = true">
        <el-icon><Plus /></el-icon> 新建日程
      </button>
    </div>

    <!-- Date Filter -->
    <div class="filter-bar">
      <el-input
        v-model="dateFilter"
        type="date"
        size="small"
        clearable
        placeholder="按日期筛选"
        style="width: 200px"
      />
    </div>

    <!-- Create Modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h3>新建日程</h3>
        <div class="form-group">
          <label>标题</label>
          <input v-model="form.title" placeholder="日程标题" class="form-input" />
        </div>
        <div class="form-group">
          <label>日期</label>
          <input v-model="form.date" type="date" class="form-input" />
        </div>
        <div class="form-group">
          <label>时间</label>
          <input v-model="form.time" type="time" class="form-input" />
        </div>
        <div class="form-group">
          <label>时长（分钟）</label>
          <input v-model.number="form.duration" type="number" min="1" class="form-input" />
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createEvent" :disabled="!form.title || !form.date">创建</button>
        </div>
      </div>
    </div>

    <!-- Calendar List -->
    <div class="event-list">
      <div v-for="day in groupedEvents" :key="day.date" class="day-section">
        <h3 class="day-title">{{ day.date }}</h3>
        <div class="event-items">
          <div v-for="evt in day.events" :key="evt.id" class="event-card">
            <div class="event-time">{{ evt.time }}</div>
            <div class="event-info">
              <div class="event-title">{{ evt.title }}</div>
              <div class="event-meta">{{ evt.duration }} 分钟</div>
            </div>
            <div class="event-actions">
              <button class="btn btn-small btn-danger" @click="deleteEvent(evt.id)">删除</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="!groupedEvents.length" class="empty">
        {{ dateFilter ? '该日期无日程' : '暂无日程' }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { get, post, del } from '../api.js'

const events = ref([])
const showCreate = ref(false)
const dateFilter = ref('')
const form = ref({ title: '', date: '', time: '09:00', duration: 60 })

const groupedEvents = computed(() => {
  let items = events.value
  if (dateFilter.value) {
    items = items.filter(e => e.date === dateFilter.value)
  }
  const groups = {}
  for (const evt of items) {
    if (!groups[evt.date]) groups[evt.date] = []
    groups[evt.date].push(evt)
  }
  return Object.keys(groups)
    .sort()
    .map(date => ({ date, events: groups[date] }))
})

onMounted(fetchEvents)

async function fetchEvents() {
  try {
    const data = await get('/api/data/calendar')
    events.value = data.items || []
  } catch (e) {
    ElMessage.error('加载日程失败: ' + e.message)
  }
}

async function createEvent() {
  if (!form.value.title || !form.value.date) return
  try {
    await post('/api/data/calendar', { data: { ...form.value } })
    showCreate.value = false
    form.value = { title: '', date: '', time: '09:00', duration: 60 }
    await fetchEvents()
    ElMessage.success('日程已创建')
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  }
}

async function deleteEvent(id) {
  try {
    await ElMessageBox.confirm('确认删除该日程？', '删除日程', {
      type: 'warning',
      confirmButtonText: '确认删除',
    })
  } catch { return }
  try {
    await del(`/api/data/calendar/${id}`)
    await fetchEvents()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}
</script>

<style scoped>
.page { max-width: 768px; margin: 0 auto; padding: 32px 24px; height: 100vh; overflow-y: auto; }
.page-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;
}
.page-header h1 { font-size: 24px; font-weight: 400; }

.filter-bar { margin-bottom: 20px; }

/* Day sections */
.day-section { margin-bottom: 24px; }
.day-title { font-size: 16px; font-weight: 500; margin-bottom: 12px; color: var(--text-secondary); }
.event-items { display: flex; flex-direction: column; gap: 8px; }
.event-card {
  display: flex; align-items: center; gap: 16px;
  padding: 14px 16px; background: var(--bg-secondary);
  border: 1px solid var(--border-primary); border-radius: 10px;
}
.event-time { font-size: 14px; color: var(--text-tertiary); min-width: 50px; }
.event-info { flex: 1; }
.event-title { font-size: 15px; margin-bottom: 4px; }
.event-meta { font-size: 13px; color: var(--text-tertiary); }
.event-actions { display: flex; gap: 6px; }

/* Empty */
.empty { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 14px; }

/* Button */
.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger { color: var(--danger); border-color: var(--danger-bg); }
.btn-danger:hover { background: var(--danger-bg); }
.btn-small { padding: 6px 12px; font-size: 12px; }

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
.form-input {
  width: 100%; padding: 10px 12px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: var(--bg-tertiary); color: var(--text-primary); font-size: 14px;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
</style>
