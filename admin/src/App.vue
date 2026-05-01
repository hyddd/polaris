<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" style="background: #304156">
      <div style="padding: 20px; color: #fff; font-size: 18px; font-weight: bold;">
        Polaris Admin
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item index="/">
          <el-icon><ChatDotRound /></el-icon>
          <span>Chat</span>
        </el-menu-item>
        <el-menu-item index="/sessions">
          <el-icon><Notebook /></el-icon>
          <span>Sessions</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <span>Config</span>
        </el-menu-item>
        <el-menu-item index="/data">
          <el-icon><Document /></el-icon>
          <span>Data</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main style="padding: 0; overflow: hidden">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
</style>
