<template>
  <el-collapse>
    <el-collapse-item :title="`Tool: ${step.name}`">
      <pre class="args">{{ JSON.stringify(step.args, null, 2) }}</pre>
      <div class="result">{{ step.result }}</div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
defineProps({ step: Object })
</script>

<style scoped>
.args { font-size: 12px; color: #666; margin: 4px 0; }
.result { font-size: 13px; color: #333; margin-top: 4px; }
</style>
