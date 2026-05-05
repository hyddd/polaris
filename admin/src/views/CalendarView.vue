<template>
  <div class="page">
    <div class="page-header">
      <h1>日程管理</h1>
      <button class="btn btn-primary btn-small" @click="openCreateModal()">
        <el-icon><Plus /></el-icon> 新建日程
      </button>
    </div>

    <!-- Month Navigation -->
    <div class="month-nav">
      <button class="btn btn-icon" @click="prevMonth">
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <h2 class="month-title">{{ currentYear }}年{{ currentMonth + 1 }}月</h2>
      <button class="btn btn-icon" @click="nextMonth">
        <el-icon><ArrowRight /></el-icon>
      </button>
      <button class="btn btn-small" @click="goToday">今天</button>
    </div>

    <!-- Calendar Grid -->
    <div class="calendar-container">
      <!-- Weekday Headers -->
      <div class="weekday-headers">
        <div v-for="day in weekdays" :key="day" class="weekday-header">{{ day }}</div>
      </div>

      <!-- Days Grid -->
      <div class="days-grid">
        <div
          v-for="(day, index) in calendarDays"
          :key="index"
          class="day-cell"
          :class="{
            'other-month': !day.isCurrentMonth,
            'today': day.isToday,
            'selected': selectedDate === day.dateStr,
            'has-events': day.events.length > 0
          }"
          @click="selectDate(day)"
        >
          <div class="day-number">{{ day.day }}</div>
          <div class="day-events">
            <div
              v-for="(event, idx) in day.events.slice(0, 2)"
              :key="event.id"
              class="event-dot"
              :title="event.title"
            >
              <span class="event-title-mini">{{ event.title }}</span>
            </div>
            <div v-if="day.events.length > 2" class="event-more">
              +{{ day.events.length - 2 }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Selected Date Panel -->
    <div v-if="selectedDate" class="selected-panel">
      <div class="panel-header">
        <h3>{{ selectedDate }}</h3>
        <button class="btn btn-small btn-primary" @click="openCreateModal(selectedDate)">
          新建日程
        </button>
      </div>
      <div class="panel-events">
        <div v-if="!selectedDateEvents.length" class="empty-day">
          该日无日程
        </div>
        <div
          v-for="event in selectedDateEvents"
          :key="event.id"
          class="event-card"
          @click="showEventDetail(event)"
        >
          <div class="event-time">{{ event.time }}</div>
          <div class="event-info">
            <div class="event-title">{{ event.title }}</div>
            <div class="event-meta">{{ event.duration }} 分钟</div>
          </div>
          <div class="event-actions">
            <button class="btn btn-small btn-danger" @click.stop="deleteEvent(event.id)">删除</button>
          </div>
        </div>
      </div>
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

    <!-- Event Detail Modal -->
    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal">
        <h3>日程详情</h3>
        <div class="detail-content">
          <div class="detail-row">
            <span class="detail-label">标题：</span>
            <span>{{ detailEvent.title }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">日期：</span>
            <span>{{ detailEvent.date }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">时间：</span>
            <span>{{ detailEvent.time }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">时长：</span>
            <span>{{ detailEvent.duration }} 分钟</span>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showDetail = false">关闭</button>
        </div>
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
const showDetail = ref(false)
const detailEvent = ref(null)
const selectedDate = ref(null)

// Month navigation
const today = new Date()
const currentYear = ref(today.getFullYear())
const currentMonth = ref(today.getMonth()) // 0-based

const form = ref({ title: '', date: '', time: '09:00', duration: 60 })

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

// Calendar days computation
const calendarDays = computed(() => {
  const year = currentYear.value
  const month = currentMonth.value

  // First day of month (0=Sun, 1=Mon, ...)
  const firstDay = new Date(year, month, 1).getDay()
  // Convert to Mon=0, Tue=1, ..., Sun=6
  const startOffset = firstDay === 0 ? 6 : firstDay - 1

  // Days in month
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  // Days in previous month
  const daysInPrevMonth = new Date(year, month, 0).getDate()

  const days = []

  // Previous month days
  for (let i = startOffset - 1; i >= 0; i--) {
    const day = daysInPrevMonth - i
    const prevMonth = month === 0 ? 11 : month - 1
    const prevYear = month === 0 ? year - 1 : year
    const dateStr = `${prevYear}-${String(prevMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    days.push({
      day,
      dateStr,
      isCurrentMonth: false,
      isToday: false,
      events: getEventsForDate(dateStr)
    })
  }

  // Current month days
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    days.push({
      day,
      dateStr,
      isCurrentMonth: true,
      isToday: dateStr === todayStr,
      events: getEventsForDate(dateStr)
    })
  }

  // Next month days (fill to complete weeks)
  const remaining = 42 - days.length // 6 rows * 7 days
  for (let day = 1; day <= remaining; day++) {
    const nextMonth = month === 11 ? 0 : month + 1
    const nextYear = month === 11 ? year + 1 : year
    const dateStr = `${nextYear}-${String(nextMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    days.push({
      day,
      dateStr,
      isCurrentMonth: false,
      isToday: false,
      events: getEventsForDate(dateStr)
    })
  }

  return days
})

// Get events for a specific date
function getEventsForDate(dateStr) {
  return events.value.filter(e => e.date === dateStr)
}

// Selected date events
const selectedDateEvents = computed(() => {
  if (!selectedDate.value) return []
  return getEventsForDate(selectedDate.value)
})

// Navigation
function prevMonth() {
  if (currentMonth.value === 0) {
    currentMonth.value = 11
    currentYear.value--
  } else {
    currentMonth.value--
  }
}

function nextMonth() {
  if (currentMonth.value === 11) {
    currentMonth.value = 0
    currentYear.value++
  } else {
    currentMonth.value++
  }
}

function goToday() {
  currentYear.value = today.getFullYear()
  currentMonth.value = today.getMonth()
  selectedDate.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
}

// Date selection
function selectDate(day) {
  selectedDate.value = day.dateStr
}

// Modal functions
function openCreateModal(date = null) {
  form.value = {
    title: '',
    date: date || selectedDate.value || '',
    time: '09:00',
    duration: 60
  }
  showCreate.value = true
}

function showEventDetail(event) {
  detailEvent.value = event
  showDetail.value = true
}

// API functions
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
.page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 32px 24px;
  height: 100vh;
  overflow-y: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 400;
}

/* Month Navigation */
.month-nav {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.month-title {
  font-size: 20px;
  font-weight: 500;
  min-width: 140px;
  text-align: center;
}

/* Calendar Container */
.calendar-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 24px;
}

/* Weekday Headers */
.weekday-headers {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-primary);
}

.weekday-header {
  padding: 12px;
  text-align: center;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

/* Days Grid */
.days-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--border-primary);
}

.day-cell {
  background: var(--bg-secondary);
  min-height: 100px;
  padding: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.day-cell:hover {
  background: var(--bg-tertiary);
}

.day-cell.other-month {
  background: var(--bg-tertiary);
  opacity: 0.6;
}

.day-cell.today {
  background: var(--accent-bg);
}

.day-cell.today .day-number {
  background: var(--accent);
  color: #fff;
  border-radius: 50%;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.day-cell.selected {
  background: var(--bg-tertiary);
  box-shadow: inset 0 0 0 2px var(--accent);
}

.day-number {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.day-cell.other-month .day-number {
  color: var(--text-tertiary);
}

/* Events in day cell */
.day-events {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.event-dot {
  background: var(--accent-bg);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: var(--accent);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-title-mini {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-more {
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 2px 6px;
}

/* Selected Date Panel */
.selected-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
  background: var(--bg-tertiary);
}

.panel-header h3 {
  font-size: 16px;
  font-weight: 500;
}

.panel-events {
  padding: 12px;
}

.empty-day {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 14px;
}

.event-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.event-card:hover {
  background: var(--bg-tertiary);
}

.event-time {
  font-size: 14px;
  color: var(--text-tertiary);
  min-width: 50px;
}

.event-info {
  flex: 1;
}

.event-title {
  font-size: 15px;
  margin-bottom: 4px;
}

.event-meta {
  font-size: 13px;
  color: var(--text-tertiary);
}

.event-actions {
  display: flex;
  gap: 6px;
}

/* Button */
.btn {
  padding: 8px 16px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn:hover {
  background: var(--bg-tertiary);
}

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-danger {
  color: var(--danger);
  border-color: var(--danger-bg);
}

.btn-danger:hover {
  background: var(--danger-bg);
}

.btn-small {
  padding: 6px 12px;
  font-size: 12px;
}

.btn-icon {
  padding: 8px;
  border: none;
  background: transparent;
}

.btn-icon:hover {
  background: var(--bg-tertiary);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  padding: 24px;
  width: 400px;
  max-width: 90vw;
}

.modal h3 {
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 16px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 14px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

/* Detail Modal */
.detail-content {
  margin-bottom: 20px;
}

.detail-row {
  display: flex;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-primary);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-label {
  font-size: 13px;
  color: var(--text-secondary);
  width: 60px;
}
</style>
