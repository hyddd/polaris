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
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import katex from 'katex'
import ToolStep from './ToolStep.vue'

const props = defineProps({ msg: Object })
const contentRef = ref(null)

function renderMath(html) {
  // Block math: $$...$$
  html = html.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => {
    try { return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false }) }
    catch { return `$$${tex}$$` }
  })
  // Inline math: $...$
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
.assistant .avatar { background: #1b7c5a; color: #fff; }

.content-wrapper { flex: 1; min-width: 0; }
.content { font-size: 15px; line-height: 1.7; color: #ececec; }
.tools { margin-bottom: 12px; }

/* Markdown */
.markdown-body p { margin: 0 0 12px; }
.markdown-body p:last-child { margin-bottom: 0; }
.markdown-body code {
  background: #1a1a1a; padding: 2px 6px; border-radius: 4px;
  font-size: 14px; font-family: 'SF Mono', Monaco, monospace;
}
.markdown-body pre {
  background: #1a1a1a; padding: 12px 16px; border-radius: 8px;
  overflow-x: auto; margin: 8px 0;
}
.markdown-body pre code { background: transparent; padding: 0; }
.markdown-body ul, .markdown-body ol { padding-left: 24px; margin: 8px 0; }
.markdown-body li { margin: 4px 0; }
.markdown-body blockquote {
  border-left: 3px solid #424242; padding-left: 12px; color: #b4b4b4; margin: 8px 0;
}
.markdown-body h1, .markdown-body h2, .markdown-body h3 { margin: 16px 0 8px; font-weight: 600; }
.markdown-body h1 { font-size: 20px; }
.markdown-body h2 { font-size: 18px; }
.markdown-body h3 { font-size: 16px; }
.markdown-body table { border-collapse: collapse; margin: 8px 0; width: 100%; }
.markdown-body th, .markdown-body td { border: 1px solid #333; padding: 8px 12px; text-align: left; }
.markdown-body th { background: #1a1a1a; }
.markdown-body hr { border: none; border-top: 1px solid #333; margin: 16px 0; }
.markdown-body a { color: #6b9eff; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body strong { font-weight: 600; }

/* KaTeX overrides for dark theme */
.katex { color: #ececec; }
.katex-display { margin: 12px 0; overflow-x: auto; }
</style>
