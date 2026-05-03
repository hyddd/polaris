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
      <div class="content markdown-body" ref="contentRef"></div>
      <div v-if="!msg.pending" class="actions">
        <button v-if="msg.role === 'user'" class="action-btn" @click="$emit('edit', msg)" title="编辑">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="m18.5 2.5 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
        </button>
        <button v-if="msg.role === 'user'" class="action-btn" @click="$emit('retry', msg)" title="重试">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/>
            <path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import katex from 'katex'
import ToolStep from './ToolStep.vue'

const props = defineProps({ msg: Object })
defineEmits(['edit', 'retry'])
const contentRef = ref(null)

function renderMath(html) {
  html = html.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => {
    try { return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false }) }
    catch { return `$$${tex}$$` }
  })
  html = html.replace(/\$([^\$\n]+?)\$/g, (_, tex) => {
    try { return katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false }) }
    catch { return `$${tex}$` }
  })
  return html
}

function updateContent() {
  if (!contentRef.value) return
  const raw = props.msg.content || ''
  const html = marked.parse(raw, { breaks: true })
  contentRef.value.innerHTML = renderMath(html)
}

onMounted(updateContent)
watch(() => props.msg.content, () => nextTick(updateContent))
</script>

<style>
@import 'katex/dist/katex.min.css';

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
.assistant .avatar { background: var(--success); color: #fff; }

.content-wrapper { flex: 1; min-width: 0; }
.content { font-size: 15px; line-height: 1.7; color: var(--text-primary); }
.tools { margin-bottom: 12px; }

.actions {
  display: flex; gap: 4px; margin-top: 8px;
  opacity: 0; transition: opacity 0.2s;
}
.message:hover .actions { opacity: 1; }
.action-btn {
  background: none; border: 1px solid var(--border-secondary); border-radius: 4px;
  padding: 4px 6px; cursor: pointer; color: var(--text-secondary);
  display: flex; align-items: center; justify-content: center;
}
.action-btn:hover {
  background: var(--bg-tertiary); color: var(--text-primary);
}

/* Markdown */
.markdown-body p { margin: 0 0 12px; }
.markdown-body p:last-child { margin-bottom: 0; }
.markdown-body code {
  background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;
  font-size: 14px; font-family: 'SF Mono', Monaco, monospace;
}
.markdown-body pre {
  background: var(--bg-tertiary); padding: 12px 16px; border-radius: 8px;
  overflow-x: auto; margin: 8px 0;
}
.markdown-body pre code { background: transparent; padding: 0; }
.markdown-body ul, .markdown-body ol { padding-left: 24px; margin: 8px 0; }
.markdown-body li { margin: 4px 0; }
.markdown-body blockquote {
  border-left: 3px solid var(--border-primary); padding-left: 12px; color: var(--text-secondary); margin: 8px 0;
}
.markdown-body h1, .markdown-body h2, .markdown-body h3 { margin: 16px 0 8px; font-weight: 600; }
.markdown-body h1 { font-size: 20px; }
.markdown-body h2 { font-size: 18px; }
.markdown-body h3 { font-size: 16px; }
.markdown-body table { border-collapse: collapse; margin: 8px 0; width: 100%; }
.markdown-body th, .markdown-body td { border: 1px solid var(--border-secondary); padding: 8px 12px; text-align: left; }
.markdown-body th { background: var(--bg-tertiary); }
.markdown-body hr { border: none; border-top: 1px solid var(--border-primary); margin: 16px 0; }
.markdown-body a { color: var(--accent); text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body strong { font-weight: 600; }

/* KaTeX */
.katex { color: var(--text-primary); }
.katex-display { margin: 12px 0; overflow-x: auto; }
</style>
