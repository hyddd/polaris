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
        <router-link to="/notes" class="sidebar-link">
          <el-icon><Memo /></el-icon> 笔记
        </router-link>
        <router-link to="/reminders" class="sidebar-link">
          <el-icon><Bell /></el-icon> 提醒
        </router-link>
        <router-link to="/status" class="sidebar-link">
          <el-icon><Monitor /></el-icon> 状态
        </router-link>
        <div class="theme-options">
          <div class="theme-slider" :style="sliderStyle"></div>
          <button class="theme-btn" @click="theme.setMode('light')" title="浅色">
            <el-icon><Sunny /></el-icon>
          </button>
          <button class="theme-btn" @click="theme.setMode('dark')" title="深色">
            <el-icon><Moon /></el-icon>
          </button>
          <button class="theme-btn" @click="theme.setMode('system')" title="跟随系统">
            <el-icon><Monitor /></el-icon>
          </button>
        </div>
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
import { useChatStore } from './stores/chat.js'
import { useThemeStore } from './stores/theme.js'
import { useRouter, useRoute } from 'vue-router'

const store = useSessionsStore()
const chatStore = useChatStore()
const theme = useThemeStore()
const router = useRouter()
const route = useRoute()

const sessions = computed(() => store.sessions)
const activeId = computed(() => store.activeId)

const sliderIndex = computed(() => {
  if (theme.mode === 'light') return 0
  if (theme.mode === 'dark') return 1
  return 2
})
const sliderStyle = computed(() => ({
  transform: `translateX(${sliderIndex.value * 100}%)`,
}))

onMounted(async () => {
  theme.init()
  await store.fetch()
  if (store.activeId) chatStore.loadSession(store.activeId)
})

async function switchSession(sid) {
  await store.switchTo(sid)
  chatStore.loadSession(sid)
  if (route.path !== '/') router.push('/')
}

async function newChat() {
  try {
    await store.create(`对话 ${store.sessions.length + 1}`)
    chatStore.clearMessages()
    if (route.path !== '/') router.push('/')
  } catch {
    // error already alerted in store
  }
}
</script>

<style>
/* CSS Variables - Dark Theme (default) */
:root, [data-theme="dark"] {
  --bg-primary: #212121;
  --bg-secondary: #2f2f2f;
  --bg-tertiary: #1a1a1a;
  --bg-sidebar: #171717;
  --border-primary: #424242;
  --border-secondary: #333;
  --text-primary: #ececec;
  --text-secondary: #b4b4b4;
  --text-tertiary: #8e8e8e;
  --accent: #3b6bed;
  --accent-hover: #4a7af0;
  --success: #1b7c5a;
  --danger: #ef4444;
  --danger-bg: #7f1d1d;
}

/* CSS Variables - Light Theme */
[data-theme="light"] {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --bg-tertiary: #e5e5e5;
  --bg-sidebar: #f9f9f9;
  --border-primary: #e0e0e0;
  --border-secondary: #d4d4d4;
  --text-primary: #1a1a1a;
  --text-secondary: #525252;
  --text-tertiary: #737373;
  --accent: #3b6bed;
  --accent-hover: #2563eb;
  --success: #16a34a;
  --danger: #dc2626;
  --danger-bg: #fecaca;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif;
  background: var(--bg-primary); color: var(--text-primary);
}

.app-layout { display: flex; height: 100vh; }

/* Sidebar */
.sidebar {
  width: 260px; background: var(--bg-sidebar); display: flex; flex-direction: column;
  border-right: 1px solid var(--border-primary); flex-shrink: 0;
}
.new-chat-btn {
  margin: 12px; padding: 10px; background: transparent; border: 1px solid var(--border-primary);
  border-radius: 8px; color: var(--text-primary); cursor: pointer; font-size: 14px;
  display: flex; align-items: center; gap: 8px; transition: background 0.2s;
}
.new-chat-btn:hover { background: var(--bg-secondary); }

.chat-history { flex: 1; overflow-y: auto; padding: 0 8px; }
.history-item {
  padding: 10px 12px; border-radius: 8px; cursor: pointer; font-size: 14px;
  color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.2s;
}
.history-item:hover { background: var(--bg-secondary); color: var(--text-primary); }
.history-item.active { background: var(--bg-secondary); color: var(--text-primary); }

.sidebar-bottom {
  padding: 8px; border-top: 1px solid var(--border-primary);
}
.sidebar-link {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border-radius: 8px; color: var(--text-secondary); text-decoration: none; font-size: 14px;
  transition: background 0.2s; border: none; background: transparent; cursor: pointer; width: 100%;
}
.sidebar-link:hover { background: var(--bg-secondary); color: var(--text-primary); }

/* Main */
.main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* Theme options */
.theme-options {
  display: flex; position: relative; padding: 4px; margin: 8px 12px 0;
  background: var(--bg-tertiary); border-radius: 10px;
}
.theme-slider {
  position: absolute; top: 4px; left: 4px;
  width: calc(33.333% - 2.67px); height: calc(100% - 8px);
  background: var(--bg-secondary); border-radius: 8px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.theme-btn {
  flex: 1; padding: 8px; border: none; border-radius: 8px;
  background: transparent; color: var(--text-tertiary); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: color 0.2s; position: relative; z-index: 1;
}
.theme-btn:hover { color: var(--text-primary); }
</style>
