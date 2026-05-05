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
      <div class="todo-header">
        <button class="btn btn-primary btn-small" @click="showCreateTodo = true">
          <el-icon><Plus /></el-icon> 新建待办
        </button>
      </div>

      <!-- Create Todo Modal -->
      <div v-if="showCreateTodo" class="modal-overlay" @click.self="showCreateTodo = false">
        <div class="modal">
          <h3>新建待办</h3>
          <div class="form-group">
            <label>标题</label>
            <input v-model="todoForm.title" placeholder="待办标题" class="form-input" />
          </div>
          <div class="form-group">
            <label>优先级</label>
            <select v-model="todoForm.priority" class="form-input">
              <option value="low">低</option>
              <option value="medium">中</option>
              <option value="high">高</option>
            </select>
          </div>
          <div class="form-group">
            <label>截止日期</label>
            <input v-model="todoForm.due" type="date" class="form-input" />
          </div>
          <div class="modal-actions">
            <button class="btn" @click="showCreateTodo = false">取消</button>
            <button class="btn btn-primary" @click="createTodo" :disabled="!todoForm.title">创建</button>
          </div>
        </div>
      </div>

      <!-- Edit Todo Modal -->
      <div v-if="editingTodo" class="modal-overlay" @click.self="editingTodo = null">
        <div class="modal">
          <h3>编辑待办</h3>
          <div class="form-group">
            <label>标题</label>
            <input v-model="editForm.title" placeholder="待办标题" class="form-input" />
          </div>
          <div class="form-group">
            <label>优先级</label>
            <select v-model="editForm.priority" class="form-input">
              <option value="low">低</option>
              <option value="medium">中</option>
              <option value="high">高</option>
            </select>
          </div>
          <div class="form-group">
            <label>状态</label>
            <select v-model="editForm.status" class="form-input">
              <option value="pending">待处理</option>
              <option value="in_progress">进行中</option>
              <option value="done">已完成</option>
            </select>
          </div>
          <div class="modal-actions">
            <button class="btn" @click="editingTodo = null">取消</button>
            <button class="btn btn-primary" @click="updateTodo" :disabled="!editForm.title">保存</button>
          </div>
        </div>
      </div>

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
          <div class="todo-actions">
            <button class="btn btn-small" @click="startEditTodo(todo)">编辑</button>
            <button class="btn btn-small btn-danger" @click="deleteItem(todo.id)">删除</button>
          </div>
        </div>
        <div v-if="!items.length" class="empty">暂无待办事项</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { get, post, put, del } from '../api.js'

const activeTab = ref('calendar')
const items = ref([])
const showCreateTodo = ref(false)
const editingTodo = ref(null)
const todoForm = ref({ title: '', priority: 'medium', due: '' })
const editForm = ref({ title: '', priority: 'medium', status: 'pending' })

async function loadData() {
  const data = await get(`/api/data/${activeTab.value}`)
  items.value = data.items || []
}

async function deleteItem(id) {
  if (!confirm('确认删除？')) return
  await del(`/api/data/${activeTab.value}/${id}`)
  await loadData()
}

async function createTodo() {
  if (!todoForm.value.title) return
  try {
    await post('/api/data/todos', { data: todoForm.value })
    showCreateTodo.value = false
    todoForm.value = { title: '', priority: 'medium', due: '' }
    await loadData()
    ElMessage.success('待办已创建')
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  }
}

function startEditTodo(todo) {
  editingTodo.value = todo
  editForm.value = { title: todo.title, priority: todo.priority, status: todo.status }
}

async function updateTodo() {
  if (!editForm.value.title || !editingTodo.value) return
  try {
    await put(`/api/data/todos/${editingTodo.value.id}`, { data: editForm.value })
    editingTodo.value = null
    await loadData()
    ElMessage.success('待办已更新')
  } catch (e) {
    ElMessage.error('更新失败: ' + e.message)
  }
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
  transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger { color: var(--danger); border-color: var(--danger-bg); }
.btn-danger:hover { background: var(--danger-bg); }
.btn-small { padding: 6px 12px; font-size: 12px; }

/* Todo Header */
.todo-header { margin-bottom: 16px; }
.todo-actions { display: flex; gap: 6px; margin-left: 12px; }

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
