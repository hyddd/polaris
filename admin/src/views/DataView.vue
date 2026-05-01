<template>
  <div style="padding: 20px;">
    <h2>Data Management</h2>

    <el-tabs v-model="activeTab" @tab-change="loadData">
      <el-tab-pane label="Calendar" name="calendar" />
      <el-tab-pane label="Todos" name="todos" />
    </el-tabs>

    <!-- Calendar -->
    <template v-if="activeTab === 'calendar'">
      <div v-for="day in items" :key="day.date" style="margin-bottom: 16px;">
        <h3>{{ day.date }}</h3>
        <el-table :data="day.events" stripe size="small">
          <el-table-column prop="time" label="Time" width="80" />
          <el-table-column prop="title" label="Title" />
          <el-table-column prop="duration" label="Duration" width="80" />
        </el-table>
      </div>
    </template>

    <!-- Todos -->
    <template v-if="activeTab === 'todos'">
      <el-table :data="items" stripe>
        <el-table-column prop="title" label="Title" />
        <el-table-column prop="priority" label="Priority" width="100">
          <template #default="{ row }">
            <el-tag :type="row.priority === 'high' ? 'danger' : row.priority === 'medium' ? 'warning' : 'info'" size="small">
              {{ row.priority }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'done' ? 'success' : 'default'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="due" label="Due" width="120" />
        <el-table-column label="Actions" width="120">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="deleteItem(row.id)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, del } from '../api.js'
import { ElMessageBox } from 'element-plus'

const activeTab = ref('calendar')
const items = ref([])

async function loadData() {
  const data = await get(`/api/data/${activeTab.value}`)
  items.value = data.items || []
}

async function deleteItem(id) {
  await ElMessageBox.confirm('Delete this item?', 'Confirm')
  await del(`/api/data/${activeTab.value}/${id}`)
  await loadData()
}

onMounted(loadData)
</script>
