<template>
  <div class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div v-if="instance" class="instance-badge" :title="instanceTitle">
        <span :class="['instance-mode', instance.mode]">{{ instance.mode_label }}</span>
        <span class="instance-name">{{ instance.name }}</span>
      </div>
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
        <router-link to="/calendar" class="sidebar-link">
          <el-icon><Calendar /></el-icon> 日程
        </router-link>
        <router-link to="/todos" class="sidebar-link">
          <el-icon><Finished /></el-icon> 待办
        </router-link>
        <router-link to="/notes" class="sidebar-link">
          <el-icon><Memo /></el-icon> 笔记
        </router-link>
        <router-link to="/knowledge" class="sidebar-link">
          <el-icon><Collection /></el-icon> 知识库
        </router-link>
        <router-link to="/reminders" class="sidebar-link">
          <el-icon><Bell /></el-icon> 提醒
        </router-link>
        <router-link to="/notify" class="sidebar-link">
          <el-icon><Promotion /></el-icon> 通知
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
import { computed, onMounted, ref } from 'vue'
import { useSessionsStore } from './stores/sessions.js'
import { useChatStore } from './stores/chat.js'
import { useThemeStore } from './stores/theme.js'
import { useRouter, useRoute } from 'vue-router'
import { get } from './api.js'

const store = useSessionsStore()
const chatStore = useChatStore()
const theme = useThemeStore()
const router = useRouter()
const route = useRoute()

const sessions = computed(() => store.sessions)
const instance = ref(null)
const instanceTitle = computed(() => {
  const i = instance.value
  if (!i) return ''
  if (i.mode === 'team') return '团队服务：只读写公共数据'
  return i.public ? `个人服务：私人 + 公共数据（团队服务 ${i.remote}）` : '个人服务：只有私人数据（没连团队服务）'
})
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
  get('/api/instance').then(d => { instance.value = d }).catch(() => {})
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
    chatStore.sessionId = store.activeId
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

.instance-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 4px 10px;
  font-size: 12px;
  color: var(--text-secondary, #999);
  overflow: hidden;
  white-space: nowrap;
}
.instance-mode {
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(64, 158, 255, 0.15);
  color: #409eff;
}
.instance-mode.team {
  background: rgba(230, 162, 60, 0.15);
  color: #e6a23c;
}
.instance-name {
  overflow: hidden;
  text-overflow: ellipsis;
}
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
