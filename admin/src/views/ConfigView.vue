<template>
  <div class="page">
    <div class="page-header">
      <h1>配置管理</h1>
      <div class="hint">修改后需执行 /reload 热重载生效</div>
    </div>

    <div class="config-list">
      <div v-for="row in configList" :key="row.key" class="config-row">
        <div class="config-key">{{ row.key }}</div>
        <div class="config-value">
          <input v-if="row.editing" v-model="row.newValue" class="dark-input" />
          <span v-else>{{ row.value }}</span>
        </div>
        <div class="config-actions">
          <button v-if="!row.editing" class="btn btn-small" @click="row.editing = true; row.newValue = row.value">编辑</button>
          <template v-else>
            <button class="btn btn-small btn-primary" @click="save(row)">保存</button>
            <button class="btn btn-small" @click="row.editing = false">取消</button>
          </template>
        </div>
      </div>
    </div>

    <button class="btn" style="margin-top: 16px;" @click="addVar">
      <el-icon><Plus /></el-icon> 添加变量
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api.js'

const configList = ref([])

onMounted(async () => {
  const data = await get('/api/config')
  configList.value = Object.entries(data.vars || {}).map(([key, value]) => ({
    key, value, newValue: value, editing: false
  }))
})

async function save(row) {
  await post('/api/config', { vars: { [row.key]: row.newValue } })
  row.value = row.newValue
  row.editing = false
}

function addVar() {
  configList.value.push({ key: '', value: '', newValue: '', editing: true })
}
</script>

<style scoped>
.page { max-width: 768px; margin: 0 auto; padding: 32px 24px; height: 100vh; overflow-y: auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 400; margin-bottom: 8px; }
.hint { font-size: 13px; color: #8e8e8e; }

.config-list { display: flex; flex-direction: column; gap: 1px; background: var(--border-primary); border-radius: 12px; overflow: hidden; }
.config-row {
  display: flex; align-items: center; padding: 12px 16px; background: var(--bg-secondary);
}
.config-key { width: 280px; font-size: 14px; color: var(--text-secondary); font-family: 'SF Mono', Monaco, monospace; }
.config-value { flex: 1; font-size: 14px; }
.config-actions { width: 120px; display: flex; gap: 8px; justify-content: flex-end; }

.dark-input {
  width: 100%; padding: 6px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-primary);
  border-radius: 6px; color: var(--text-primary); font-size: 14px; outline: none;
}
.dark-input:focus { border-color: var(--accent); }

.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-small { padding: 6px 12px; font-size: 12px; }
</style>
