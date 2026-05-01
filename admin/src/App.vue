<template>
  <div class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <button class="new-chat-btn" @click="newChat">
        <el-icon><Plus /></el-icon> 新对话
      </button>
      <div class="chat-history">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          :class="['history-item', { active: s.session_id === activeId }]"
          @click="switchSession(s.session_id)"
        >
          {{ s.name }}
        </div>
      </div>
      <div class="sidebar-bottom">
        <router-link to="/sessions" class="sidebar-link">
          <el-icon><Notebook /></el-icon> 会话管理
        </router-link>
        <router-link to="/config" class="sidebar-link">
          <el-icon><Setting /></el-icon> 配置
        </router-link>
        <router-link to="/data" class="sidebar-link">
          <el-icon><Document /></el-icon> 数据
        </router-link>
      </div>
    </aside>

    <!-- Main -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useSessionsStore } from './stores/sessions.js'
import { useRouter, useRoute } from 'vue-router'

const store = useSessionsStore()
const router = useRouter()
const route = useRoute()

const sessions = computed(() => store.sessions)
const activeId = computed(() => store.activeId)

onMounted(() => store.fetch())

async function switchSession(sid) {
  await store.switchTo(sid)
  if (route.path !== '/') router.push('/')
}

async function newChat() {
  await store.create(`对话 ${store.sessions.length + 1}`)
  if (route.path !== '/') router.push('/')
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #212121; color: #ececec; }

.app-layout { display: flex; height: 100vh; }

/* Sidebar */
.sidebar {
  width: 260px; background: #171717; display: flex; flex-direction: column;
  border-right: 1px solid #2f2f2f; flex-shrink: 0;
}
.new-chat-btn {
  margin: 12px; padding: 10px; background: transparent; border: 1px solid #424242;
  border-radius: 8px; color: #ececec; cursor: pointer; font-size: 14px;
  display: flex; align-items: center; gap: 8px; transition: background 0.2s;
}
.new-chat-btn:hover { background: #2f2f2f; }

.chat-history { flex: 1; overflow-y: auto; padding: 0 8px; }
.history-item {
  padding: 10px 12px; border-radius: 8px; cursor: pointer; font-size: 14px;
  color: #b4b4b4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.2s;
}
.history-item:hover { background: #2f2f2f; color: #ececec; }
.history-item.active { background: #2f2f2f; color: #fff; }

.sidebar-bottom {
  padding: 8px; border-top: 1px solid #2f2f2f;
}
.sidebar-link {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border-radius: 8px; color: #b4b4b4; text-decoration: none; font-size: 14px;
  transition: background 0.2s;
}
.sidebar-link:hover { background: #2f2f2f; color: #ececec; }

/* Main */
.main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
</style>
