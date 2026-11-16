<template>
  <div class="page">
    <div class="page-header">
      <h1>系统状态</h1>
      <button class="btn" @click="refresh">
        <el-icon><Refresh /></el-icon> 刷新
      </button>
    </div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else class="status-grid">
      <!-- Instance -->
      <div class="status-card" v-if="status.instance">
        <h3>服务模式</h3>
        <div class="status-list">
          <div class="status-item">
            <span class="status-name">{{ status.instance.mode_label }} · {{ status.instance.name }}</span>
            <span :class="['badge', status.instance.mode === 'team' ? 'badge-warning' : 'badge-success']">
              {{ status.instance.mode === 'team' ? '只有公共数据' : (status.instance.public ? '私人 + 公共' : '只有私人数据') }}
            </span>
          </div>
          <div v-if="status.team" class="status-item">
            <span class="status-name">团队服务 {{ status.team.url }}</span>
            <span :class="['badge', status.team.ok ? 'badge-success' : 'badge-warning']">
              {{ status.team.ok ? `已连接：${status.team.name}` : '连不上' }}
            </span>
          </div>
          <div v-if="status.team && !status.team.ok" class="empty-hint">{{ status.team.error }}</div>
        </div>
      </div>

      <!-- Channels -->
      <div class="status-card">
        <h3>通道状态</h3>
        <div v-if="!status.channels?.length" class="empty-hint">暂无通道</div>
        <div v-else class="status-list">
          <div v-for="ch in status.channels" :key="ch.name" class="status-item">
            <span class="status-name">{{ ch.name }}</span>
            <span :class="['badge', ch.configured ? 'badge-success' : 'badge-warning']">
              {{ ch.configured ? '已配置' : '未配置' }}
            </span>
          </div>
        </div>
      </div>

      <!-- Tools -->
      <div class="status-card">
        <h3>已注册工具</h3>
        <div v-if="!status.tools?.length" class="empty-hint">暂无工具</div>
        <div v-else class="status-list">
          <div v-for="t in status.tools" :key="t.name" class="status-item">
            <span class="status-name">{{ t.name }}</span>
          </div>
        </div>
      </div>

      <!-- Scheduled Jobs -->
      <div class="status-card">
        <h3>定时任务</h3>
        <div v-if="!status.jobs?.length" class="empty-hint">暂无定时任务</div>
        <div v-else class="status-list">
          <div v-for="job in status.jobs" :key="job.id" class="status-item">
            <div class="job-info">
              <span class="status-name">{{ job.name }}</span>
              <span class="job-meta">{{ job.trigger_type }} · {{ job.handler_type }}</span>
            </div>
            <span :class="['badge', job.enabled ? 'badge-success' : 'badge-warning']">
              {{ job.enabled ? '启用' : '禁用' }}
            </span>
          </div>
        </div>
      </div>

      <!-- Active Reminders -->
      <div class="status-card">
        <h3>活跃提醒</h3>
        <div v-if="!activeReminders.length" class="empty-hint">暂无活跃提醒</div>
        <div v-else class="status-list">
          <div v-for="r in activeReminders" :key="r.id" class="status-item">
            <div class="job-info">
              <span class="status-name">{{ r.title }}</span>
              <span class="job-meta">{{ formatTime(r.trigger_time) }} · {{ repeatLabel(r.repeat_rule) }}</span>
            </div>
            <span class="badge badge-success">活跃</span>
          </div>
        </div>
      </div>

      <!-- Metrics -->
      <div class="status-card">
        <h3>Metrics 快照</h3>
        <div v-if="!metrics.counters && !metrics.timers" class="empty-hint">暂无数据</div>
        <div v-else>
          <div v-if="metrics.counters && Object.keys(metrics.counters).length" class="metrics-section">
            <h4>计数器</h4>
            <div class="metrics-grid">
              <div v-for="(val, key) in metrics.counters" :key="key" class="metric-item">
                <span class="metric-name">{{ key }}</span>
                <span class="metric-value">{{ val }}</span>
              </div>
            </div>
          </div>
          <div v-if="metrics.timers && Object.keys(metrics.timers).length" class="metrics-section">
            <h4>计时器</h4>
            <div class="metrics-grid">
              <div v-for="(val, key) in metrics.timers" :key="key" class="metric-item">
                <span class="metric-name">{{ key }}</span>
                <span class="metric-value">{{ val.avg_ms }}ms ({{ val.count }}次)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { get } from '../api.js'

const status = ref({})
const metrics = ref({})
const reminders = ref([])
const loading = ref(true)

const activeReminders = computed(() => {
  const now = new Date()
  return reminders.value.filter(r => {
    if (r.status === 'cancelled') return false
    // 过期的一次性提醒不显示
    if (r.repeat_rule === 'none' && new Date(r.trigger_time) < now) return false
    return true
  })
})

onMounted(refresh)

async function refresh() {
  loading.value = true
  try {
    const [s, m, r] = await Promise.all([
      get('/api/status'),
      get('/api/metrics'),
      get('/api/reminders'),
    ])
    status.value = s
    metrics.value = m
    reminders.value = r.items || []
  } catch (e) {
    ElMessage.error('加载状态失败: ' + e.message)
  } finally {
    loading.value = false
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
</script>

<style scoped>
.page { max-width: 900px; margin: 0 auto; padding: 32px 24px; height: 100vh; overflow-y: auto; }
.page-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;
}
.page-header h1 { font-size: 24px; font-weight: 400; }

.status-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 16px;
}

.status-card {
  background: var(--bg-secondary); border: 1px solid var(--border-primary);
  border-radius: 12px; padding: 20px;
}
.status-card h3 {
  font-size: 16px; font-weight: 500; margin-bottom: 16px;
  padding-bottom: 12px; border-bottom: 1px solid var(--border-primary);
}

.status-list { display: flex; flex-direction: column; gap: 8px; }
.status-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0;
}
.status-name { font-size: 14px; }
.job-info { display: flex; flex-direction: column; gap: 2px; }
.job-meta { font-size: 12px; color: var(--text-tertiary); }

.badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  font-weight: 500;
}
.badge-success { background: #14532d; color: #86efac; }
.badge-warning { background: #78350f; color: #fcd34d; }

.metrics-section { margin-bottom: 16px; }
.metrics-section:last-child { margin-bottom: 0; }
.metrics-section h4 {
  font-size: 13px; font-weight: 500; color: var(--text-secondary);
  margin-bottom: 8px;
}
.metrics-grid { display: flex; flex-direction: column; gap: 6px; }
.metric-item {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px;
}
.metric-name { color: var(--text-secondary); }
.metric-value { font-family: monospace; color: var(--text-primary); }

.empty-hint { text-align: center; padding: 20px; color: var(--text-tertiary); font-size: 13px; }
.empty { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 14px; }

.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
</style>
