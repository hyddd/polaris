<template>
  <div class="knowledge-layout">
    <!-- Left Panel: Document List -->
    <div class="doc-list-panel">
      <div class="list-header">
        <h2>知识库</h2>
        <button class="btn btn-primary btn-small" @click="showUpload = true">
          <el-icon><Upload /></el-icon> 上传
        </button>
      </div>

      <!-- Upload Area -->
      <div v-if="showUpload" class="upload-area">
        <div
          class="upload-dropzone"
          :class="{ dragging }"
          @dragover.prevent="dragging = true"
          @dragleave="dragging = false"
          @drop.prevent="handleDrop"
          @click="triggerFileInput"
        >
          <el-icon :size="32" color="var(--text-tertiary)"><Upload /></el-icon>
          <p>拖拽文件到此处，或点击选择</p>
          <p class="upload-hint">支持 PDF、DOCX、TXT、MD 格式</p>
        </div>
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.docx,.txt,.md,.markdown"
          style="display: none"
          @change="handleFileSelect"
        />
        <div v-if="uploading" class="upload-progress">
          <el-icon class="is-loading"><Loading /></el-icon>
          上传中...
        </div>
        <button class="btn btn-small" @click="showUpload = false">取消</button>
      </div>

      <!-- Document List -->
      <div class="doc-items">
        <div
          v-for="doc in documents"
          :key="doc.doc_id"
          :class="['doc-item', { active: doc.doc_id === activeDocId }]"
          @click="activeDocId = doc.doc_id"
        >
          <div class="doc-item-name">{{ doc.filename }}</div>
          <div class="doc-item-meta">
            <span>{{ doc.chunk_count }} 个分块</span>
            <span v-for="tag in doc.tags" :key="tag" class="doc-tag">{{ tag }}</span>
          </div>
          <div class="doc-item-time">{{ formatTime(doc.created_at) }}</div>
        </div>
        <div v-if="documents.length === 0" class="empty-hint">
          暂无文档，点击上方按钮上传
        </div>
      </div>

      <!-- Delete Button -->
      <div v-if="activeDocId" class="doc-actions">
        <button class="btn btn-danger btn-small" @click="handleDelete">
          <el-icon><Delete /></el-icon> 删除文档
        </button>
      </div>
    </div>

    <!-- Right Panel: Search -->
    <div class="search-panel">
      <div class="search-header">
        <h3>语义搜索</h3>
        <div class="search-box">
          <el-input
            v-model="searchQuery"
            placeholder="输入关键词搜索知识库..."
            clearable
            @keyup.enter="doSearch"
          >
            <template #append>
              <el-button @click="doSearch">
                <el-icon><Search /></el-icon>
              </el-button>
            </template>
          </el-input>
        </div>
      </div>

      <!-- Search Results -->
      <div class="search-results">
        <div v-if="searching" class="searching-hint">
          <el-icon class="is-loading"><Loading /></el-icon>
          搜索中...
        </div>
        <div v-else-if="searchResults.length > 0">
          <div v-for="(result, idx) in searchResults" :key="idx" class="result-item">
            <div class="result-header">
              <span class="result-title">{{ result.title || '未命名' }}</span>
              <span class="result-score">相关度: {{ (result.score * 100).toFixed(0) }}%</span>
            </div>
            <div class="result-content">{{ result.content }}</div>
          </div>
        </div>
        <div v-else-if="searched" class="empty-hint">
          没有找到相关结果
        </div>
        <div v-else class="empty-state">
          <el-icon :size="48" color="var(--text-tertiary)"><Search /></el-icon>
          <p>输入关键词搜索知识库</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { get, post, del } from '../api.js'

const documents = ref([])
const activeDocId = ref('')
const showUpload = ref(false)
const uploading = ref(false)
const dragging = ref(false)
const fileInput = ref(null)

const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
const searched = ref(false)

onMounted(fetchDocuments)

async function fetchDocuments() {
  try {
    const data = await get('/api/knowledge')
    documents.value = data.items || []
  } catch (e) {
    ElMessage.error('加载文档列表失败: ' + e.message)
  }
}

function triggerFileInput() {
  fileInput.value?.click()
}

function handleDrop(e) {
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadFile(file)
}

function handleFileSelect(e) {
  const file = e.target.files?.[0]
  if (file) uploadFile(file)
  e.target.value = ''
}

async function uploadFile(file) {
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await fetch('/api/knowledge/upload', {
      method: 'POST',
      body: formData,
    })
    if (!result.ok) {
      const err = await result.json()
      throw new Error(err.detail || '上传失败')
    }
    const data = await result.json()
    ElMessage.success(`上传成功: ${data.filename} (${data.chunk_count} 个分块)`)
    showUpload.value = false
    await fetchDocuments()
  } catch (e) {
    ElMessage.error('上传失败: ' + e.message)
  } finally {
    uploading.value = false
  }
}

async function handleDelete() {
  if (!activeDocId.value) return
  const doc = documents.value.find(d => d.doc_id === activeDocId.value)
  try {
    await ElMessageBox.confirm(
      `确认删除文档 "${doc?.filename || activeDocId.value}"？删除后不可恢复。`,
      '删除文档',
      { type: 'warning', confirmButtonText: '确认删除' }
    )
  } catch {
    return
  }
  try {
    await del(`/api/knowledge/${activeDocId.value}`)
    documents.value = documents.value.filter(d => d.doc_id !== activeDocId.value)
    activeDocId.value = ''
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

async function doSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  searched.value = false
  try {
    const data = await get(`/api/knowledge/search?q=${encodeURIComponent(searchQuery.value)}`)
    searchResults.value = data.items || []
    searched.value = true
  } catch (e) {
    ElMessage.error('搜索失败: ' + e.message)
  } finally {
    searching.value = false
  }
}

function formatTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}
</script>

<style scoped>
.knowledge-layout {
  display: flex; height: 100vh; overflow: hidden;
}

/* Document List Panel */
.doc-list-panel {
  width: 300px; flex-shrink: 0; background: var(--bg-sidebar);
  border-right: 1px solid var(--border-primary); display: flex; flex-direction: column;
}
.list-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 16px 12px;
}
.list-header h2 { font-size: 18px; font-weight: 500; }

/* Upload Area */
.upload-area {
  padding: 12px; border-bottom: 1px solid var(--border-primary);
}
.upload-dropzone {
  border: 2px dashed var(--border-primary); border-radius: 8px;
  padding: 24px 16px; text-align: center; cursor: pointer;
  transition: all 0.2s;
}
.upload-dropzone:hover, .upload-dropzone.dragging {
  border-color: var(--accent); background: var(--bg-secondary);
}
.upload-dropzone p {
  margin: 8px 0 0; font-size: 13px; color: var(--text-secondary);
}
.upload-hint { font-size: 12px; color: var(--text-tertiary); }
.upload-progress {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 0; font-size: 13px; color: var(--text-secondary);
}

/* Document Items */
.doc-items {
  flex: 1; overflow-y: auto; padding: 8px;
}
.doc-item {
  padding: 12px; border-radius: 8px; cursor: pointer; margin-bottom: 4px;
  transition: background 0.2s;
}
.doc-item:hover { background: var(--bg-secondary); }
.doc-item.active { background: var(--bg-secondary); }
.doc-item-name {
  font-size: 14px; color: var(--text-primary); margin-bottom: 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.doc-item-meta {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-size: 12px; color: var(--text-tertiary);
}
.doc-tag {
  font-size: 11px; padding: 1px 6px; border-radius: 4px;
  background: var(--bg-tertiary); color: var(--text-secondary);
}
.doc-item-time {
  font-size: 11px; color: var(--text-tertiary); margin-top: 4px;
}

/* Document Actions */
.doc-actions {
  padding: 12px; border-top: 1px solid var(--border-primary);
}

/* Search Panel */
.search-panel {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  background: var(--bg-primary);
}
.search-header {
  padding: 16px 24px; border-bottom: 1px solid var(--border-primary);
}
.search-header h3 { font-size: 16px; font-weight: 500; margin-bottom: 12px; }
.search-box { max-width: 600px; }

/* Search Results */
.search-results {
  flex: 1; overflow-y: auto; padding: 16px 24px;
}
.searching-hint {
  display: flex; align-items: center; gap: 8px;
  padding: 32px 0; color: var(--text-secondary);
}
.result-item {
  padding: 16px; margin-bottom: 12px;
  border: 1px solid var(--border-primary); border-radius: 8px;
  background: var(--bg-secondary);
}
.result-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.result-title { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.result-score { font-size: 12px; color: var(--accent); }
.result-content {
  font-size: 13px; color: var(--text-secondary); line-height: 1.6;
  max-height: 200px; overflow-y: auto; white-space: pre-wrap;
}

/* Empty States */
.empty-hint {
  text-align: center; padding: 32px 16px; color: var(--text-tertiary); font-size: 13px;
}
.empty-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
}
.empty-state p { color: var(--text-tertiary); font-size: 14px; }

/* Buttons */
.btn {
  padding: 8px 16px; border: 1px solid var(--border-primary); border-radius: 8px;
  background: transparent; color: var(--text-primary); font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--bg-tertiary); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-danger { background: var(--danger); border-color: var(--danger); color: #fff; }
.btn-danger:hover { opacity: 0.9; }
.btn-small { padding: 6px 12px; font-size: 12px; }
</style>
