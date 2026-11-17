<template>
  <div class="page">
    <div class="page-header">
      <h1>通知</h1>
      <button class="btn" @click="loadTargets">
        <el-icon><Refresh /></el-icon> 刷新目标
      </button>
    </div>

    <div class="data-content">
      <!-- 令牌：服务端设置了 notify.api_token 时需要 -->
      <div v-if="needToken" class="card">
        <div class="hint">此服务设置了通知接口令牌（notify.api_token），请输入后继续。令牌只保存在当前浏览器中。</div>
        <div class="row">
          <input v-model="tokenInput" type="password" placeholder="notify.api_token" class="form-input" />
          <button class="btn btn-primary" @click="saveToken" :disabled="!tokenInput">保存</button>
        </div>
      </div>

      <div v-else-if="loading" class="empty">加载中...</div>

      <template v-else>
        <div class="form-group">
          <label>发送给</label>
          <div v-if="!targets.length" class="empty-hint">
            没有配置通知目标。请在服务的 config.local.yaml 中配置 notify.webhooks（企业微信群机器人）或 notify.recipients（QQ / 飞书）。
          </div>
          <div v-else class="target-list">
            <label v-for="t in targets" :key="t.name" :class="['target', { disabled: !t.available }]" :title="t.reason || ''">
              <input type="checkbox" :value="t.name" v-model="selected" :disabled="!t.available" />
              <span class="target-name">{{ t.name }}</span>
              <span class="badge">{{ typeLabel(t.type) }}</span>
              <span v-if="!t.available" class="target-reason">{{ t.reason }}</span>
            </label>
          </div>
        </div>

        <div class="form-group">
          <label>标题</label>
          <input v-model="title" maxlength="200" placeholder="通知标题" class="form-input" />
        </div>
        <div class="form-group">
          <label>正文</label>
          <textarea v-model="content" maxlength="4000" placeholder="通知内容（企业微信支持 markdown）" class="form-textarea" />
        </div>

        <div class="actions">
          <button class="btn btn-primary" @click="send" :disabled="sending || !selected.length || (!title && !content)">
            {{ sending ? '发送中...' : '发送' }}
          </button>
          <button v-if="token" class="btn btn-small" @click="clearToken">清除已保存的令牌</button>
        </div>

        <div v-if="error" class="result result-fail">{{ error }}</div>
        <div v-if="results.length" class="results">
          <div v-for="r in results" :key="r.target" :class="['result', r.ok ? 'result-ok' : 'result-fail']">
            {{ r.target }}：{{ r.ok ? '已发送' : '失败，' + (r.error || '') }}
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const TOKEN_KEY = 'polaris.notifyToken'
const token = ref(localStorage.getItem(TOKEN_KEY) || '')
const tokenInput = ref('')
const needToken = ref(false)
const loading = ref(true)
const targets = ref([])
const selected = ref([])
const title = ref('')
const content = ref('')
const sending = ref(false)
const results = ref([])
const error = ref('')

function typeLabel(type) {
  return { wecom: '企业微信群', qq: 'QQ', feishu: '飞书私聊', 'feishu-chat': '飞书群' }[type] || type
}

async function call(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (token.value) headers.Authorization = `Bearer ${token.value}`
  const r = await fetch(path, { ...options, headers })
  if (r.status === 401) {
    needToken.value = true
    throw new Error('令牌错误或缺失')
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
  return data
}

async function loadTargets() {
  loading.value = true
  error.value = ''
  try {
    const data = await call('/api/notify/targets')
    targets.value = data.targets || []
    selected.value = selected.value.filter(n => targets.value.some(t => t.name === n && t.available))
  } catch (e) {
    if (!needToken.value) error.value = e.message
  } finally {
    loading.value = false
  }
}

function saveToken() {
  token.value = tokenInput.value.trim()
  localStorage.setItem(TOKEN_KEY, token.value)
  tokenInput.value = ''
  needToken.value = false
  loadTargets()
}

function clearToken() {
  token.value = ''
  localStorage.removeItem(TOKEN_KEY)
  loadTargets()
}

async function send() {
  sending.value = true
  error.value = ''
  results.value = []
  try {
    const data = await call('/api/notify/send', {
      method: 'POST',
      body: JSON.stringify({ targets: selected.value, title: title.value, content: content.value, source: '网页' }),
    })
    results.value = data.results || []
  } catch (e) {
    error.value = e.message
  } finally {
    sending.value = false
  }
}

onMounted(loadTargets)
</script>

<style scoped>
.page { max-width: 768px; margin: 0 auto; padding: 32px 24px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 400; }
.data-content { flex: 1; overflow-y: auto; min-height: 0; }

.card {
  padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
  border-radius: 10px; margin-bottom: 16px;
}
.hint, .empty-hint { font-size: 13px; color: var(--text-tertiary); margin-bottom: 10px; }
.row { display: flex; gap: 8px; }

.form-group { margin-bottom: 16px; }
.form-group > label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.form-input, .form-textarea {
  width: 100%; padding: 10px 12px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: var(--bg-tertiary); color: var(--text-primary); font-size: 14px;
}
.form-textarea { min-height: 140px; resize: vertical; }

.target-list { display: flex; flex-direction: column; gap: 6px; }
.target {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: pointer;
  background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px;
}
.target.disabled { opacity: 0.55; cursor: not-allowed; }
.target-name { font-size: 14px; }
.target-reason { font-size: 12px; color: var(--text-tertiary); margin-left: auto; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #1e3a5f; color: #93c5fd; }

.actions { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
.results { display: flex; flex-direction: column; gap: 6px; }
.result { font-size: 13px; padding: 8px 12px; border-radius: 8px; }
.result-ok { background: #14532d; color: #86efac; }
.result-fail { background: #7f1d1d; color: #fca5a5; margin-bottom: 6px; }
.empty { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 14px; }

.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-small { padding: 6px 12px; font-size: 12px; }
</style>
