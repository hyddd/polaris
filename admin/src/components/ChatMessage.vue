<template>
  <div :class="['message', msg.role]">
    <div class="bubble">
      <div v-if="msg.tools?.length" class="tools">
        <ToolStep v-for="t in msg.tools" :key="t.call_id" :step="t" />
      </div>
      <div class="content" v-html="formatContent(msg.content)"></div>
    </div>
  </div>
</template>

<script setup>
import ToolStep from './ToolStep.vue'
defineProps({ msg: Object })

function formatContent(text) {
  if (!text) return ''
  return text.replace(/\n/g, '<br>')
}
</script>

<style scoped>
.message { display: flex; margin: 8px 16px; }
.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }
.bubble {
  max-width: 70%; padding: 10px 14px; border-radius: 12px;
  font-size: 14px; line-height: 1.6;
}
.user .bubble { background: #409eff; color: #fff; border-bottom-right-radius: 4px; }
.assistant .bubble { background: #f4f4f5; color: #333; border-bottom-left-radius: 4px; }
.tools { margin-bottom: 8px; }
</style>
