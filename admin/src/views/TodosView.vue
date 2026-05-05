<template>
  <div class="page">
    <div class="page-header">
      <h1>待办管理</h1>
      <button class="btn btn-primary btn-small" @click="showCreate = true">
        <el-icon><Plus /></el-icon> 新建待办
      </button>
    </div>

    <!-- Status Filter -->
    <div class="filter-tabs">
      <button :class="['tab', { active: statusFilter === 'all' }]" @click="statusFilter = 'all'">全部</button>
      <button :class="['tab', { active: statusFilter === 'pending' }]" @click="statusFilter = 'pending'">待处理</button>
      <button :class="['tab', { active: statusFilter === 'in_progress' }]" @click="statusFilter = 'in_progress'">进行中</button>
      <button :class="['tab', { active: statusFilter === 'done' }]" @click="statusFilter = 'done'">已完成</button>
    </div>

    <!-- Create Modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h3>新建待办</h3>
        <div class="form-group">
          <label>标题</label>
          <input v-model="createForm.title" placeholder="待办标题" class="form-input" />
        </div>
        <div class="form-group">
          <label>优先级</label>
          <select v-model="createForm.priority" class="form-input">
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
          </select>
        </div>
        <div class="form-group">
          <label>截止日期</label>
          <input v-model="createForm.due" type="date" class="form-input" />
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createTodo" :disabled="!createForm.title">创建</button>
        </div>
      </div>
    </div>

    <!-- Edit Modal -->
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

    <!-- Todo List -->
    <div class="todo-list">
      <div v-for="todo in filteredTodos" :key="todo.id" :class="['todo-card', { done: todo.status === 'done' }]">
        <div class="todo-main">
          <div class="todo-title">{{ todo.title }}</div>
          <div class="todo-meta">
            <span :class="['badge', `priority-${todo.priority}`]">{{ priorityLabel(todo.priority) }}</span>
            <span :class="['badge', `status-${todo.status}`]">{{ statusLabel(todo.status) }}</span>
            <span v-if="todo.due" class="todo-due">截止: {{ todo.due }}</span>
          </div>
        </div>
        <div class="todo-actions">
          <button v-if="todo.status !== 'done'" class="btn btn-small btn-success" @click="markDone(todo)">完成</button>
          <button class="btn btn-small" @click="startEdit(todo)">编辑</button>
          <button class="btn btn-small btn-danger" @click="deleteTodo(todo.id)">删除</button>
        </div>
      </div>
      <div v-if="!filteredTodos.length" class="empty">
        {{ statusFilter === 'all' ? '暂无待办事项' : '该状态下无待办' }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { get, post, put, del } from '../api.js'

const todos = ref([])
const showCreate = ref(false)
const editingTodo = ref(null)
const statusFilter = ref('all')
const createForm = ref({ title: '', priority: 'medium', due: '' })
const editForm = ref({ title: '', priority: 'medium', status: 'pending' })

const filteredTodos = computed(() => {
  if (statusFilter.value === 'all') return todos.value
  return todos.value.filter(t => t.status === statusFilter.value)
})

const priorityLabels = { low: '低', medium: '中', high: '高' }
const statusLabels = { pending: '待处理', in_progress: '进行中', done: '已完成' }

function priorityLabel(p) { return priorityLabels[p] || p }
function statusLabel(s) { return statusLabels[s] || s }

onMounted(fetchTodos)

async function fetchTodos() {
  try {
    const data = await get('/api/data/todos')
    todos.value = data.items || []
  } catch (e) {
    ElMessage.error('加载待办失败: ' + e.message)
  }
}

async function createTodo() {
  if (!createForm.value.title) return
  try {
    await post('/api/data/todos', { data: { ...createForm.value } })
    showCreate.value = false
    createForm.value = { title: '', priority: 'medium', due: '' }
    await fetchTodos()
    ElMessage.success('待办已创建')
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  }
}

function startEdit(todo) {
  editingTodo.value = todo
  editForm.value = { title: todo.title, priority: todo.priority, status: todo.status }
}

async function updateTodo() {
  if (!editForm.value.title || !editingTodo.value) return
  try {
    await put(`/api/data/todos/${editingTodo.value.id}`, { data: { ...editForm.value } })
    editingTodo.value = null
    await fetchTodos()
    ElMessage.success('待办已更新')
  } catch (e) {
    ElMessage.error('更新失败: ' + e.message)
  }
}

async function markDone(todo) {
  try {
    await put(`/api/data/todos/${todo.id}`, { data: { status: 'done' } })
    await fetchTodos()
    ElMessage.success('已标记完成')
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function deleteTodo(id) {
  try {
    await ElMessageBox.confirm('确认删除该待办？', '删除待办', {
      type: 'warning',
      confirmButtonText: '确认删除',
    })
  } catch { return }
  try {
    await del(`/api/data/todos/${id}`)
    await fetchTodos()
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

/* Filter Tabs */
.filter-tabs {
  display: flex; gap: 4px; margin-bottom: 20px;
  background: var(--bg-tertiary); border-radius: 10px; padding: 4px;
}
.tab {
  flex: 1; padding: 8px 16px; border: none; border-radius: 8px;
  background: transparent; color: var(--text-tertiary); font-size: 14px; cursor: pointer;
  transition: all 0.2s;
}
.tab.active { background: var(--bg-secondary); color: var(--text-primary); }
.tab:hover:not(.active) { color: var(--text-secondary); }

/* Todo List */
.todo-list { display: flex; flex-direction: column; gap: 8px; }
.todo-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 16px; background: var(--bg-secondary);
  border: 1px solid var(--border-primary); border-radius: 10px;
}
.todo-card.done { opacity: 0.6; }
.todo-title { font-size: 15px; margin-bottom: 8px; }
.todo-card.done .todo-title { text-decoration: line-through; }
.todo-meta { display: flex; gap: 8px; align-items: center; }
.todo-due { font-size: 13px; color: var(--text-tertiary); }
.todo-actions { display: flex; gap: 6px; margin-left: 12px; }

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
.btn-success { color: var(--success); border-color: var(--success); }
.btn-success:hover { background: rgba(27, 124, 90, 0.15); }
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
