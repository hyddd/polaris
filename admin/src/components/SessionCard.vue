<template>
  <el-card shadow="hover" :class="{ active: isActive }">
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span>
          <el-tag v-if="isActive" type="success" size="small">Active</el-tag>
          {{ session.name }}
        </span>
        <span style="color: #999; font-size: 12px;">{{ session.session_id }}</span>
      </div>
    </template>
    <div style="font-size: 13px; color: #666;">
      Messages: {{ session.message_count || 0 }}
    </div>
    <div style="margin-top: 12px;">
      <el-button v-if="!isActive" size="small" type="primary" @click="$emit('switch', session.session_id)">Switch</el-button>
      <el-button size="small" @click="$emit('rename', session.session_id)">Rename</el-button>
      <el-button v-if="!isActive" size="small" type="danger" @click="$emit('delete', session.session_id)">Delete</el-button>
    </div>
  </el-card>
</template>

<script setup>
defineProps({ session: Object, isActive: Boolean })
defineEmits(['switch', 'rename', 'delete'])
</script>

<style scoped>
.el-card { margin-bottom: 12px; }
.active { border-color: #409eff; }
</style>
