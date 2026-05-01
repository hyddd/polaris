<template>
  <div style="padding: 20px;">
    <div style="display: flex; justify-content: space-between; margin-bottom: 16px;">
      <h2>Session Management</h2>
      <el-button type="primary" @click="showCreate = true">New Session</el-button>
    </div>

    <SessionCard
      v-for="s in store.sessions"
      :key="s.session_id"
      :session="s"
      :is-active="s.session_id === store.activeId"
      @switch="store.switchTo"
      @rename="handleRename"
      @delete="handleDelete"
    />

    <el-dialog v-model="showCreate" title="New Session">
      <el-input v-model="newName" placeholder="Session name" />
      <template #footer>
        <el-button @click="showCreate = false">Cancel</el-button>
        <el-button type="primary" @click="create">Create</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useSessionsStore } from '../stores/sessions.js'
import SessionCard from '../components/SessionCard.vue'

const store = useSessionsStore()
const showCreate = ref(false)
const newName = ref('')

onMounted(() => store.fetch())

async function create() {
  if (newName.value.trim()) {
    await store.create(newName.value.trim())
    newName.value = ''
    showCreate.value = false
  }
}

async function handleDelete(sid) {
  await ElMessageBox.confirm('Delete this session?', 'Confirm')
  await store.remove(sid)
}

async function handleRename(sid) {
  const { value } = await ElMessageBox.prompt('New name', 'Rename')
  if (value) await store.rename(sid, value)
}
</script>
