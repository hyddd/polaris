<template>
  <div style="padding: 20px;">
    <h2>Configuration</h2>
    <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
      Changes require /reload to take effect
    </el-alert>

    <el-table :data="configList" stripe>
      <el-table-column prop="key" label="Variable" width="300" />
      <el-table-column prop="value" label="Value">
        <template #default="{ row }">
          <el-input v-if="row.editing" v-model="row.newValue" size="small" />
          <span v-else>{{ row.value }}</span>
        </template>
      </el-table-column>
      <el-table-column width="150">
        <template #default="{ row }">
          <el-button v-if="!row.editing" size="small" @click="row.editing = true; row.newValue = row.value">Edit</el-button>
          <template v-else>
            <el-button size="small" type="primary" @click="save(row)">Save</el-button>
            <el-button size="small" @click="row.editing = false">Cancel</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-button style="margin-top: 16px;" @click="addVar">Add Variable</el-button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api.js'

const configList = ref([])

onMounted(async () => {
  const data = await get('/api/config')
  configList.value = Object.entries(data.vars || {}).map(([key, value]) => ({
    key, value, newValue: value, editing: false
  }))
})

async function save(row) {
  await post('/api/config', { vars: { [row.key]: row.newValue } })
  row.value = row.newValue
  row.editing = false
}

function addVar() {
  configList.value.push({ key: '', value: '', newValue: '', editing: true })
}
</script>
