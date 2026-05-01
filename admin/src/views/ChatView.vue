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
    <div v-else class="messages" ref="messagesRef">
      <ChatMessage v-for="(msg, i) in store.messages" :key="i" :msg="msg" />
    </div>

    <!-- Input bar -->
    <div class="input-wrapper">
      <div class="input-bar">
        <textarea
          v-model="input"
          placeholder="Message Polaris"
          rows="1"
          @keydown.enter.exact.prevent="send"
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
import { ref, nextTick, watch } from 'vue'
import { useChatStore } from '../stores/chat.js'
import ChatMessage from '../components/ChatMessage.vue'

const store = useChatStore()
const input = ref('')
const messagesRef = ref(null)
const inputRef = ref(null)

const suggestions = [
  '今天有什么安排？',
  '帮我创建一个待办事项',
  '查看最近的笔记',
  '总结一下本周的工作',
]

async function send() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'
  await store.sendMessage(text)
  await nextTick()
  if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
}

function sendSuggestion(text) {
  input.value = text
  send()
}

function autoResize() {
  const el = inputRef.value
  if (el) {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }
}

watch(() => store.messages.length, () => {
  nextTick(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  })
})
</script>

<style scoped>
.chat-view { display: flex; flex-direction: column; height: 100vh; background: #212121; }

/* Welcome */
.welcome { flex: 1; display: flex; align-items: center; justify-content: center; }
.welcome-content { text-align: center; }
.welcome-content h1 { font-size: 28px; font-weight: 400; color: #ececec; margin-bottom: 32px; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 600px; }
.suggestion {
  padding: 10px 16px; background: #2f2f2f; border: 1px solid #424242; border-radius: 20px;
  color: #b4b4b4; font-size: 14px; cursor: pointer; transition: all 0.2s;
}
.suggestion:hover { background: #3a3a3a; color: #ececec; border-color: #555; }

/* Messages */
.messages { flex: 1; overflow-y: auto; padding: 0; }

/* Input */
.input-wrapper { padding: 0 24px 16px; }
.input-bar {
  display: flex; align-items: flex-end; background: #2f2f2f; border-radius: 16px;
  padding: 10px 16px; border: 1px solid #424242; transition: border-color 0.2s;
}
.input-bar:focus-within { border-color: #676767; }
.input-bar textarea {
  flex: 1; background: transparent; border: none; color: #ececec; font-size: 15px;
  resize: none; outline: none; max-height: 200px; line-height: 1.5;
  font-family: inherit;
}
.input-bar textarea::placeholder { color: #8e8e8e; }
.send-btn {
  background: transparent; border: none; color: #8e8e8e; cursor: pointer;
  padding: 4px; border-radius: 8px; display: flex; align-items: center;
  transition: color 0.2s;
}
.send-btn:hover:not(:disabled) { color: #ececec; }
.send-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.input-hint { text-align: center; font-size: 12px; color: #8e8e8e; margin-top: 8px; }
</style>
