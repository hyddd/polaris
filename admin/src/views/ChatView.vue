<template>
  <div class="chat-view">
    <div class="messages" ref="messagesRef">
      <ChatMessage v-for="(msg, i) in store.messages" :key="i" :msg="msg" />
      <div v-if="store.loading" class="typing">Polaris is thinking...</div>
    </div>
    <div class="input-bar">
      <el-input
        v-model="input"
        placeholder="Type a message..."
        @keydown.enter.prevent="send"
        :disabled="store.loading"
      >
        <template #append>
          <el-button @click="send" :disabled="store.loading || !input.trim()">
            Send
          </el-button>
        </template>
      </el-input>
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

async function send() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  await store.sendMessage(text)
  await nextTick()
  messagesRef.value.scrollTop = messagesRef.value.scrollHeight
}

watch(() => store.messages.length, () => {
  nextTick(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  })
})
</script>

<style scoped>
.chat-view { display: flex; flex-direction: column; height: 100vh; }
.messages { flex: 1; overflow-y: auto; padding: 16px 0; }
.input-bar { padding: 12px 16px; border-top: 1px solid #e4e7ed; }
.typing { padding: 8px 16px; color: #999; font-size: 13px; }
</style>
