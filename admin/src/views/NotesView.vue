<template>
  <div class="notes-layout">
    <!-- Note List -->
    <div class="note-list-panel">
      <div class="list-header">
        <h2>笔记</h2>
        <button class="btn btn-primary btn-small" @click="startCreate">
          <el-icon><Plus /></el-icon> 新建
        </button>
      </div>
      <div class="search-box">
        <el-input
          v-model="searchQuery"
          placeholder="搜索笔记..."
          clearable
          prefix-icon="Search"
          size="small"
        />
      </div>
      <div class="note-items">
        <div
          v-for="note in filteredNotes"
          :key="note.filename"
          :class="['note-item', { active: note.filename === activeFilename }]"
          @click="selectNote(note.filename)"
        >
          <div class="note-item-title">{{ note.title }}</div>
          <div class="note-item-meta">
            <span class="note-date">{{ note.date }}</span>
            <span v-for="tag in note.tags" :key="tag" class="note-tag">{{ tag }}</span>
          </div>
        </div>
        <div v-if="filteredNotes.length === 0" class="empty-hint">
          {{ searchQuery ? '没有匹配的笔记' : '暂无笔记' }}
        </div>
      </div>
    </div>

    <!-- Note Detail -->
    <div class="note-detail-panel">
      <template v-if="activeFilename">
        <div class="detail-header">
          <div class="detail-title">{{ currentNote?.title }}</div>
          <div class="detail-actions">
            <button class="btn btn-small" @click="handleDelete" title="删除">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
        </div>

        <!-- Tags -->
        <div class="detail-tags">
          <el-tag
            v-for="tag in currentNote?.tags"
            :key="tag"
            size="small"
            closable
            @close="removeTag(tag)"
          >{{ tag }}</el-tag>
          <el-input
            v-if="showTagInput"
            ref="tagInputRef"
            v-model="newTag"
            size="small"
            style="width: 100px"
            @keyup.enter="addTag"
            @blur="addTag"
          />
          <el-button v-else size="small" @click="showTagInput = true">+ 标签</el-button>
        </div>

        <!-- Tabs: Edit / Preview -->
        <el-tabs v-model="activeTab" class="note-tabs">
          <el-tab-pane label="编辑" name="edit">
            <textarea
              v-model="editContent"
              class="note-editor"
              placeholder="输入笔记内容 (Markdown)..."
              @input="onContentChange"
            />
          </el-tab-pane>
          <el-tab-pane label="预览" name="preview">
            <div class="note-preview" v-html="renderedContent" />
          </el-tab-pane>
        </el-tabs>

        <!-- Save indicator -->
        <div v-if="dirty" class="save-bar">
          <span>未保存的更改</span>
          <button class="btn btn-primary btn-small" @click="saveNote">保存</button>
        </div>
      </template>

      <template v-else>
        <div class="empty-state">
          <el-icon :size="48" color="var(--text-tertiary)"><Notebook /></el-icon>
          <p>选择一篇笔记查看，或创建新笔记</p>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { marked } from 'marked'
import { get, post, put, del } from '../api.js'

const notes = ref([])
const activeFilename = ref('')
const currentNote = ref(null)
const editContent = ref('')
const activeTab = ref('preview')
const dirty = ref(false)
const searchQuery = ref('')
const showTagInput = ref(false)
const newTag = ref('')
const tagInputRef = ref(null)

const filteredNotes = computed(() => {
  if (!searchQuery.value) return notes.value
  const q = searchQuery.value.toLowerCase()
  return notes.value.filter(
    n => n.title.toLowerCase().includes(q) || n.tags?.some(t => t.toLowerCase().includes(q))
  )
})

const renderedContent = computed(() => {
  return marked.parse(editContent.value || '', { breaks: true })
})

onMounted(fetchNotes)

async function fetchNotes() {
  try {
    const data = await get('/api/notes')
    notes.value = data.items || []
  } catch (e) {
    ElMessage.error('加载笔记列表失败: ' + e.message)
  }
}

async function selectNote(filename) {
  if (dirty.value) {
    try {
      await ElMessageBox.confirm('当前笔记有未保存的更改，是否先保存？', '提示', {
        confirmButtonText: '保存',
        cancelButtonText: '放弃',
        type: 'warning',
      })
      await saveNote()
    } catch {
      // user chose to discard
    }
  }
  try {
    const note = await get(`/api/notes/${encodeURIComponent(filename)}`)
    currentNote.value = note
    activeFilename.value = filename
    editContent.value = note.content
    dirty.value = false
    activeTab.value = 'preview'
  } catch (e) {
    ElMessage.error('加载笔记失败: ' + e.message)
  }
}

function onContentChange() {
  dirty.value = editContent.value !== (currentNote.value?.content || '')
}

async function saveNote() {
  if (!activeFilename.value) return
  try {
    const updated = await put(`/api/notes/${encodeURIComponent(activeFilename.value)}`, {
      content: editContent.value,
    })
    currentNote.value = updated
    dirty.value = false
    // Update list item
    const idx = notes.value.findIndex(n => n.filename === activeFilename.value)
    if (idx !== -1) {
      notes.value[idx] = { ...notes.value[idx], ...updated }
    }
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  }
}

async function startCreate() {
  try {
    const { value } = await ElMessageBox.prompt('请输入笔记标题', '新建笔记', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValidator: (val) => {
        if (!val || !val.trim()) return '标题不能为空'
        return true
      },
    })
    const note = await post('/api/notes', { title: value.trim(), content: '', tags: [] })
    notes.value.unshift(note)
    selectNote(note.filename)
    ElMessage.success('笔记已创建')
  } catch {
    // user cancelled
  }
}

async function handleDelete() {
  if (!activeFilename.value) return
  try {
    await ElMessageBox.confirm('删除后不可恢复，确认删除？', '删除笔记', {
      type: 'warning',
      confirmButtonText: '确认删除',
    })
  } catch { return }
  try {
    await del(`/api/notes/${encodeURIComponent(activeFilename.value)}`)
    notes.value = notes.value.filter(n => n.filename !== activeFilename.value)
    activeFilename.value = ''
    currentNote.value = null
    editContent.value = ''
    dirty.value = false
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

function addTag() {
  const tag = newTag.value.trim()
  if (!tag || !currentNote.value) return
  if (currentNote.value.tags.includes(tag)) {
    newTag.value = ''
    showTagInput.value = false
    return
  }
  const tags = [...currentNote.value.tags, tag]
  put(`/api/notes/${encodeURIComponent(activeFilename.value)}`, { tags })
    .then(updated => {
      currentNote.value = updated
      const idx = notes.value.findIndex(n => n.filename === activeFilename.value)
      if (idx !== -1) notes.value[idx] = { ...notes.value[idx], tags: updated.tags }
    })
    .catch(e => ElMessage.error('添加标签失败: ' + e.message))
  newTag.value = ''
  showTagInput.value = false
}

function removeTag(tag) {
  if (!currentNote.value) return
  const tags = currentNote.value.tags.filter(t => t !== tag)
  put(`/api/notes/${encodeURIComponent(activeFilename.value)}`, { tags })
    .then(updated => {
      currentNote.value = updated
      const idx = notes.value.findIndex(n => n.filename === activeFilename.value)
      if (idx !== -1) notes.value[idx] = { ...notes.value[idx], tags: updated.tags }
    })
    .catch(e => ElMessage.error('移除标签失败: ' + e.message))
}
</script>

<style scoped>
.notes-layout {
  display: flex; height: 100vh; overflow: hidden;
}

/* Note List */
.note-list-panel {
  width: 280px; flex-shrink: 0; background: var(--bg-sidebar);
  border-right: 1px solid var(--border-primary); display: flex; flex-direction: column;
}
.list-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 16px 12px;
}
.list-header h2 { font-size: 18px; font-weight: 500; }
.search-box { padding: 0 12px 12px; }
.note-items { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
.note-item {
  padding: 12px; border-radius: 8px; cursor: pointer; margin-bottom: 4px;
  transition: background 0.2s;
}
.note-item:hover { background: var(--bg-secondary); }
.note-item.active { background: var(--bg-secondary); }
.note-item-title {
  font-size: 14px; color: var(--text-primary); margin-bottom: 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.note-item-meta {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.note-date { font-size: 12px; color: var(--text-tertiary); }
.note-tag {
  font-size: 11px; padding: 1px 6px; border-radius: 4px;
  background: var(--bg-tertiary); color: var(--text-secondary);
}
.empty-hint {
  text-align: center; padding: 32px 16px; color: var(--text-tertiary); font-size: 13px;
}

/* Note Detail */
.note-detail-panel {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  background: var(--bg-primary);
}
.detail-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px 0;
}
.detail-title { font-size: 20px; font-weight: 500; }
.detail-actions { display: flex; gap: 8px; }
.detail-tags {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 12px 24px 0;
}

/* Tabs */
.note-tabs {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  padding: 0 24px;
}
.note-tabs :deep(.el-tabs__header) { margin: 0; }
.note-tabs :deep(.el-tabs__content) {
  flex: 1; overflow: hidden; padding: 0;
}
.note-tabs :deep(.el-tab-pane) {
  height: 100%;
}

/* Editor */
.note-editor {
  width: 100%; height: 100%; resize: none; border: none; outline: none;
  background: var(--bg-primary); color: var(--text-primary);
  font-size: 14px; line-height: 1.8; padding: 16px 0;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}

/* Preview */
.note-preview {
  height: 100%; overflow-y: auto; padding: 16px 0;
  font-size: 14px; line-height: 1.8; color: var(--text-primary);
}
.note-preview :deep(h1) { font-size: 24px; font-weight: 600; margin: 16px 0 8px; }
.note-preview :deep(h2) { font-size: 20px; font-weight: 600; margin: 14px 0 6px; }
.note-preview :deep(h3) { font-size: 16px; font-weight: 600; margin: 12px 0 4px; }
.note-preview :deep(p) { margin: 8px 0; }
.note-preview :deep(code) {
  background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; font-size: 13px;
}
.note-preview :deep(pre) {
  background: var(--bg-tertiary); padding: 12px 16px; border-radius: 8px;
  overflow-x: auto; margin: 12px 0;
}
.note-preview :deep(pre code) { background: none; padding: 0; }
.note-preview :deep(blockquote) {
  border-left: 3px solid var(--accent); padding-left: 12px;
  color: var(--text-secondary); margin: 12px 0;
}
.note-preview :deep(ul), .note-preview :deep(ol) { padding-left: 24px; margin: 8px 0; }
.note-preview :deep(table) { border-collapse: collapse; margin: 12px 0; }
.note-preview :deep(th), .note-preview :deep(td) {
  border: 1px solid var(--border-primary); padding: 8px 12px;
}
.note-preview :deep(th) { background: var(--bg-tertiary); }
.note-preview :deep(a) { color: var(--accent); text-decoration: none; }
.note-preview :deep(a:hover) { text-decoration: underline; }
.note-preview :deep(img) { max-width: 100%; border-radius: 8px; }
.note-preview :deep(hr) {
  border: none; border-top: 1px solid var(--border-primary); margin: 16px 0;
}

/* Save bar */
.save-bar {
  display: flex; align-items: center; justify-content: flex-end; gap: 12px;
  padding: 12px 24px; border-top: 1px solid var(--border-primary);
  font-size: 13px; color: var(--text-secondary);
}

/* Empty state */
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
.btn-small { padding: 6px 12px; font-size: 12px; }
</style>
