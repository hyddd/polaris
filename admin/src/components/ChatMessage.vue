<template>
  <div :class="['message', msg.role]">
    <div class="avatar">
      <span v-if="msg.role === 'user'">U</span>
      <span v-else>P</span>
    </div>
    <div class="content-wrapper">
      <div v-if="msg.tools?.length" class="tools">
        <ToolStep v-for="t in msg.tools" :key="t.call_id || Math.random()" :step="t" />
      </div>
      <div class="content">{{ msg.content }}</div>
    </div>
  </div>
</template>

<script setup>
import ToolStep from './ToolStep.vue'
defineProps({ msg: Object })
</script>

<style scoped>
.message {
  display: flex; gap: 16px; padding: 24px 0;
  max-width: 768px; margin: 0 auto; width: 100%;
}
.message.user { padding: 16px 0; }

.avatar {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.user .avatar { background: #5b6abf; color: #fff; }
.assistant .avatar { background: #1b7c5a; color: #fff; }

.content-wrapper { flex: 1; min-width: 0; }
.content {
  font-size: 15px; line-height: 1.7; color: #ececec;
  white-space: pre-wrap; word-break: break-word;
}
.tools { margin-bottom: 12px; }
</style>
