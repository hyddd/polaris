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
        <button v-if="msg.role === 'assistant'" class="action-btn" :class="{ playing: ttsPlaying }" @click="playTTS" :disabled="ttsLoading" title="语音播放">
          <svg v-if="!ttsLoading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
            <path v-if="!ttsPlaying" d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
            <path v-if="!ttsPlaying" d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
          </svg>
        </button>
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
const ttsLoading = ref(false)
const ttsPlaying = ref(false)
let currentAudio = null

async function playTTS() {
  // 如果正在播放，停止
  if (currentAudio) {
    currentAudio.pause()
    currentAudio = null
    ttsPlaying.value = false
    return
  }

  const text = props.msg.content || ''
  if (!text.trim()) return

  ttsLoading.value = true
  try {
    const resp = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 4096) }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || 'TTS 请求失败')
    }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    currentAudio = audio
    ttsPlaying.value = true
    audio.play()
    audio.onended = () => {
      URL.revokeObjectURL(url)
      currentAudio = null
      ttsPlaying.value = false
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      currentAudio = null
      ttsPlaying.value = false
    }
  } catch (e) {
    console.error('TTS 播放失败:', e)
    currentAudio = null
    ttsPlaying.value = false
  } finally {
    ttsLoading.value = false
  }
}

function renderContent(content) {
  if (!content) return ''
  // 转义 HTML
  let html = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // 将 /api/voice URL 替换为 audio 播放器
  html = html.replace(/(\/api\/voice\/[\w]+\.(?:wav|mp3))/g, '<br><audio controls preload="none" src="$1"></audio>')
  // Markdown 粗体
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  return html
}

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
  // 先处理 audio URL（在 markdown 解析之前，避免被转义）
  const withAudio = renderContent(raw)
  // 对于包含 audio 标签的消息，跳过 markdown 解析直接使用 renderContent 结果
  if (withAudio.includes('<audio')) {
    contentRef.value.innerHTML = withAudio
    return
  }
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
.action-btn.playing {
  color: var(--accent);
  border-color: var(--accent);
}
.action-btn:disabled {
  opacity: 0.5; cursor: not-allowed;
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
