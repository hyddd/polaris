<template>
  <div class="chat-view">
    <!-- Welcome screen when no messages -->
    <div v-if="!store.messages.length" class="welcome">
      <div class="welcome-content">
        <h1>有什么可以帮你的？</h1>
        <div class="suggestions">
          <button v-for="s in suggestions" :key="s" class="suggestion" @click="sendSuggestion(s)">
            {{ s }}
          </button>
        </div>
      </div>
    </div>

    <!-- Messages -->
    <div v-else class="messages" ref="messagesRef" @scroll="onScroll">
      <div v-if="hasMore" class="load-more">
        <button class="btn-load-more" @click="loadMore" :disabled="loadingMore">
          {{ loadingMore ? '加载中...' : '加载更多' }}
        </button>
      </div>
      <ChatMessage v-for="(msg, i) in store.messages" :key="i" :msg="msg" />
      <!-- Loading indicator -->
      <div v-if="store.loading && !hasPendingMessage" class="loading-message">
        <div class="avatar assistant">P</div>
        <div class="loading-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <!-- Input bar -->
    <div class="input-wrapper">
      <div class="input-bar">
        <textarea
          v-model="input"
          placeholder="Message Polaris"
          rows="1"
          @keydown.enter.exact="onEnter"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @input="autoResize"
          ref="inputRef"
        />
        <button class="send-btn" @click="send" :disabled="store.loading || !input.trim()">
          <el-icon><Promotion /></el-icon>
        </button>
      </div>
      <div class="input-hint">Polaris 可能会犯错。请核实重要信息。</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '../stores/chat.js'
import ChatMessage from '../components/ChatMessage.vue'

const store = useChatStore()
const hasPendingMessage = computed(() => store.messages.some(m => m.role === 'assistant' && m.pending))
const hasMore = computed(() => store.messages.length < store.allMessages.length)
const input = ref('')
const messagesRef = ref(null)
const inputRef = ref(null)
const isComposing = ref(false)
const loadingMore = ref(false)

const suggestions = [
  '今天有什么安排？',
  '帮我创建一个待办事项',
  '查看最近的笔记',
  '总结一下本周的工作',
]

// Scroll to bottom on mount after messages are loaded
onMounted(() => {
  setTimeout(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }, 100)
})

function onEnter(e) {
  if (isComposing.value) return
  e.preventDefault()
  send()
}

async function send() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
    inputRef.value.focus()
  }
  await store.sendMessage(text)
  await nextTick()
  if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
}

function sendSuggestion(text) {
  input.value = text
  nextTick(() => {
    if (inputRef.value) inputRef.value.focus()
    send()
  })
}

function autoResize() {
  const el = inputRef.value
  if (el) {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }
}

async function loadMore() {
  loadingMore.value = true
  const prevHeight = messagesRef.value?.scrollHeight || 0
  store.loadMore()
  await nextTick()
  if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight - prevHeight
  loadingMore.value = false
}

function onScroll() {
  if (messagesRef.value?.scrollTop < 50 && hasMore.value && !loadingMore.value) {
    loadMore()
  }
}

// Scroll to bottom when messages are loaded or new message added
watch(() => store.messages.length, (newLen, oldLen) => {
  nextTick(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  })
}, { immediate: true })

// Auto-scroll during streaming when pending message content changes
watch(() => {
  const pending = store.messages.find(m => m.pending)
  return pending?.content
}, () => {
  nextTick(() => {
    if (messagesRef.value) {
      const { scrollTop, scrollHeight, clientHeight } = messagesRef.value
      // Only auto-scroll if user is near the bottom (within 200px)
      if (scrollHeight - scrollTop - clientHeight < 200) {
        messagesRef.value.scrollTop = scrollHeight
      }
    }
  })
})
</script>

<style scoped>
.chat-view { display: flex; flex-direction: column; height: 100vh; background: var(--bg-primary); }

/* Welcome */
.welcome { flex: 1; display: flex; align-items: center; justify-content: center; }
.welcome-content { text-align: center; }
.welcome-content h1 { font-size: 28px; font-weight: 400; color: var(--text-primary); margin-bottom: 32px; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 600px; }
.suggestion {
  padding: 10px 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 20px;
  color: var(--text-secondary); font-size: 14px; cursor: pointer; transition: all 0.2s;
}
.suggestion:hover { background: var(--bg-tertiary); color: var(--text-primary); border-color: var(--text-tertiary); }

/* Messages */
.messages { flex: 1; overflow-y: auto; padding: 0; }

/* Input */
.input-wrapper { padding: 0 24px 16px; }
.input-bar {
  display: flex; align-items: flex-end; background: var(--bg-secondary); border-radius: 16px;
  padding: 10px 16px; border: 1px solid var(--border-primary); transition: border-color 0.2s;
}
.input-bar:focus-within { border-color: var(--text-tertiary); }
.input-bar textarea {
  flex: 1; background: transparent; border: none; color: var(--text-primary); font-size: 15px;
  resize: none; outline: none; max-height: 200px; line-height: 1.5;
  font-family: inherit;
}
.input-bar textarea::placeholder { color: var(--text-tertiary); }
.send-btn {
  background: transparent; border: none; color: var(--text-tertiary); cursor: pointer;
  padding: 4px; border-radius: 8px; display: flex; align-items: center;
  transition: color 0.2s;
}
.send-btn:hover:not(:disabled) { color: var(--text-primary); }
.send-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.input-hint { text-align: center; font-size: 12px; color: var(--text-tertiary); margin-top: 8px; }

/* Loading animation */
.loading-message {
  display: flex; gap: 16px; padding: 24px;
  max-width: 768px; margin: 0 auto; width: 100%;
}
.loading-message .avatar {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; background: var(--success); color: #fff;
}
.loading-dots { display: flex; gap: 4px; align-items: center; padding: 8px 0; }
.loading-dots span {
  width: 8px; height: 8px; background: var(--text-tertiary); border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}
.loading-dots span:nth-child(1) { animation-delay: 0s; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* Load more */
.load-more { text-align: center; padding: 12px; }
.btn-load-more {
  background: transparent; border: 1px solid var(--border-primary); border-radius: 8px;
  color: var(--text-tertiary); padding: 6px 16px; font-size: 13px; cursor: pointer;
}
.btn-load-more:hover { background: var(--bg-secondary); color: var(--text-primary); }
.btn-load-more:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
