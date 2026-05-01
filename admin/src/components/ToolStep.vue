<template>
  <div class="tool-step" @click="expanded = !expanded">
    <div class="tool-header">
      <span class="tool-icon">⚡</span>
      <span class="tool-name">{{ step.name }}</span>
      <span class="tool-toggle">{{ expanded ? '▲' : '▼' }}</span>
    </div>
    <div v-if="expanded" class="tool-body">
      <pre class="args">{{ JSON.stringify(step.args, null, 2) }}</pre>
      <div class="result" v-if="step.result !== '执行中...'">{{ step.result }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
defineProps({ step: Object })
const expanded = ref(false)
</script>

<style scoped>
.tool-step {
  background: var(--bg-tertiary); border: 1px solid var(--border-secondary); border-radius: 8px;
  margin-bottom: 4px; overflow: hidden; cursor: pointer;
}
.tool-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  font-size: 13px; color: var(--text-secondary);
}
.tool-icon { font-size: 14px; }
.tool-name { flex: 1; }
.tool-toggle { font-size: 10px; color: var(--text-tertiary); }
.tool-body { padding: 0 12px 10px; }
.args { font-size: 12px; color: var(--text-tertiary); margin: 0 0 6px; white-space: pre-wrap; }
.result { font-size: 13px; color: var(--text-secondary); padding: 6px 0; border-top: 1px solid var(--border-secondary); }
</style>
