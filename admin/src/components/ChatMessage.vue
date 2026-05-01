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
      <div class="content markdown-body" v-html="renderedContent"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import ToolStep from './ToolStep.vue'

const props = defineProps({ msg: Object })

const renderedContent = computed(() => {
  if (!props.msg.content) return ''
  return marked.parse(props.msg.content, { breaks: true })
})
</script>

<style scoped>
.message {
  display: flex; gap: 16px; padding: 24px 0;
  max-width: 768px; margin: 0 auto; width: 100%;
  padding-left: 24px; padding-right: 24px;
}
.message.user { padding: 16px 0; padding-left: 24px; padding-right: 24px; }

.avatar {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.user .avatar { background: #5b6abf; color: #fff; }
.assistant .avatar { background: #1b7c5a; color: #fff; }

.content-wrapper { flex: 1; min-width: 0; }
.content { font-size: 15px; line-height: 1.7; color: #ececec; }
.tools { margin-bottom: 12px; }

/* Markdown styles */
.markdown-body :deep(p) { margin: 0 0 12px; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(code) {
  background: #1a1a1a; padding: 2px 6px; border-radius: 4px;
  font-size: 14px; font-family: 'SF Mono', Monaco, monospace;
}
.markdown-body :deep(pre) {
  background: #1a1a1a; padding: 12px 16px; border-radius: 8px;
  overflow-x: auto; margin: 8px 0;
}
.markdown-body :deep(pre code) { background: transparent; padding: 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 24px; margin: 8px 0;
}
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(blockquote) {
  border-left: 3px solid #424242; padding-left: 12px; color: #b4b4b4; margin: 8px 0;
}
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) {
  margin: 16px 0 8px; font-weight: 600;
}
.markdown-body :deep(h1) { font-size: 20px; }
.markdown-body :deep(h2) { font-size: 18px; }
.markdown-body :deep(h3) { font-size: 16px; }
.markdown-body :deep(table) {
  border-collapse: collapse; margin: 8px 0; width: 100%;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid #333; padding: 8px 12px; text-align: left;
}
.markdown-body :deep(th) { background: #1a1a1a; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid #333; margin: 16px 0; }
.markdown-body :deep(a) { color: #6b9eff; text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(strong) { font-weight: 600; }
</style>
