<template>
  <div class="page">
    <div class="page-header">
      <h1>数据管理</h1>
    </div>

    <!-- Tabs -->
    <div class="tabs">
      <button :class="['tab', { active: activeTab === 'calendar' }]" @click="activeTab = 'calendar'; loadData()">日历</button>
      <button :class="['tab', { active: activeTab === 'todos' }]" @click="activeTab = 'todos'; loadData()">待办</button>
    </div>

    <!-- Calendar -->
    <div v-if="activeTab === 'calendar'" class="data-content">
      <div v-for="day in items" :key="day.date" class="day-section">
        <h3 class="day-title">{{ day.date }}</h3>
        <div class="event-list">
          <div v-for="evt in day.events" :key="evt.id" class="event-card">
            <div class="event-time">{{ evt.time }}</div>
            <div class="event-info">
              <div class="event-title">{{ evt.title }}</div>
              <div class="event-meta">{{ evt.duration }} 分钟 · {{ evt.attendees?.join(', ') }}</div>
            </div>
          </div>
          <div v-if="!day.events?.length" class="empty">暂无日程</div>
        </div>
      </div>
      <div v-if="!items.length" class="empty">暂无日历数据</div>
    </div>

    <!-- Todos -->
    <div v-if="activeTab === 'todos'" class="data-content">
      <div class="todo-list">
        <div v-for="todo in items" :key="todo.id" class="todo-card">
          <div class="todo-main">
            <div class="todo-title">{{ todo.title }}</div>
            <div class="todo-meta">
              <span :class="['badge', `priority-${todo.priority}`]">{{ todo.priority }}</span>
              <span :class="['badge', `status-${todo.status}`]">{{ todo.status }}</span>
              <span v-if="todo.due" class="todo-due">截止: {{ todo.due }}</span>
            </div>
          </div>
          <button class="btn btn-small btn-danger" @click="deleteItem(todo.id)">删除</button>
        </div>
        <div v-if="!items.length" class="empty">暂无待办事项</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, del } from '../api.js'

const activeTab = ref('calendar')
const items = ref([])

async function loadData() {
  const data = await get(`/api/data/${activeTab.value}`)
  items.value = data.items || []
}

async function deleteItem(id) {
  if (!confirm('确认删除？')) return
  await del(`/api/data/${activeTab.value}/${id}`)
  await loadData()
}

onMounted(loadData)
</script>

<style scoped>
.page { max-width: 768px; margin: 0 auto; padding: 32px 24px; height: 100vh; overflow-y: auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 400; }

/* Tabs */
.tabs { display: flex; gap: 4px; margin-bottom: 24px; background: var(--bg-tertiary); border-radius: 10px; padding: 4px; }
.tab {
  flex: 1; padding: 8px 16px; border: none; border-radius: 8px;
  background: transparent; color: var(--text-tertiary); font-size: 14px; cursor: pointer;
  transition: all 0.2s;
}
.tab.active { background: var(--bg-secondary); color: var(--text-primary); }
.tab:hover:not(.active) { color: var(--text-secondary); }

/* Calendar */
.day-section { margin-bottom: 24px; }
.day-title { font-size: 16px; font-weight: 500; margin-bottom: 12px; color: var(--text-secondary); }
.event-list { display: flex; flex-direction: column; gap: 8px; }
.event-card {
  display: flex; gap: 16px; padding: 14px 16px; background: var(--bg-secondary);
  border: 1px solid var(--border-primary); border-radius: 10px;
}
.event-time { font-size: 14px; color: var(--text-tertiary); min-width: 50px; }
.event-title { font-size: 15px; margin-bottom: 4px; }
.event-meta { font-size: 13px; color: var(--text-tertiary); }

/* Todos */
.todo-list { display: flex; flex-direction: column; gap: 8px; }
.todo-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px;
}
.todo-title { font-size: 15px; margin-bottom: 8px; }
.todo-meta { display: flex; gap: 8px; align-items: center; }
.todo-due { font-size: 13px; color: var(--text-tertiary); }

/* Badges */
.badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  font-weight: 500; text-transform: uppercase;
}
.priority-high { background: #7f1d1d; color: #fca5a5; }
.priority-medium { background: #78350f; color: #fcd34d; }
.priority-low { background: #1e3a5f; color: #93c5fd; }
.status-done { background: #14532d; color: #86efac; }
.status-pending { background: #3f3f46; color: #a1a1aa; }
.status-in_progress { background: #1e3a5f; color: #93c5fd; }

/* Empty */
.empty { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 14px; }

/* Button */
.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-danger { color: var(--danger); border-color: var(--danger-bg); }
.btn-danger:hover { background: var(--danger-bg); }
.btn-small { padding: 6px 12px; font-size: 12px; }
</style>
