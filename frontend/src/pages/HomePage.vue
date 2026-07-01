<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePapersStore } from '@/stores/papers'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { FileText, Search, Filter, Upload, BookOpen } from 'lucide-vue-next'
import PaperCard from '@/components/PaperCard.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
const router = useRouter()
const papersStore = usePapersStore()
const authStore = useAuthStore()
const uiStore = useUIStore()
const searchQuery = ref('')
const showFilters = ref(false)

// 确认/提示弹窗（替代原生 confirm/alert）；cancelText 为空即「仅确定」的提示模式
const dialog = ref(null)
function openDialog(opts) {
  dialog.value = opts
}
function closeDialog() {
  dialog.value = null
}
function handleDialogConfirm() {
  const fn = dialog.value?.onConfirm
  closeDialog()
  if (fn) fn()
}

onMounted(async () => {
  await authStore.initialize()
  await papersStore.fetchPapers()
})

// 搜索走后端 keyword（防抖 300ms），不再只搜当前页
let searchTimer = null
watch(searchQuery, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    const kw = val.trim()
    papersStore.fetchPapers(kw ? { keyword: kw } : undefined)
  }, 300)
})

function handleViewPaper(paper) {
  router.push(`/papers/${paper.paper_id}`)
}

function handleDeletePaper(paperId) {
  openDialog({
    title: '删除论文',
    message: '确定要删除这篇论文吗？此操作不可撤销。',
    confirmText: '删除',
    cancelText: '取消',
    danger: true,
    onConfirm: async () => {
      try {
        await papersStore.deletePaper(paperId)
      } catch (err) {
        openDialog({ title: '删除失败', message: err.userMessage || '删除失败，请重试', cancelText: '' })
      }
    },
  })
}

async function handleReparse(paperId) {
  try {
    await papersStore.reparsePaper(paperId)
  } catch (err) {
    openDialog({ title: '操作失败', message: err.userMessage || '重新解析失败，请重试', cancelText: '' })
  }
}
</script>

<template>
  <div class="home-page">
    <div class="page-header">
      <div class="header-title">
        <BookOpen class="title-icon" />
        <div>
          <h1>科研文献库</h1>
          <p>管理和解析您的学术论文</p>
        </div>
      </div>

      <div v-if="authStore.isAnonymous" class="anonymous-hint">
        <span>当前为匿名模式，登录后可同步数据</span>
      </div>
    </div>

    <div class="page-actions">
      <div class="search-bar">
        <Search class="search-icon" />
        <input
          type="text"
          v-model="searchQuery"
          class="search-input"
          placeholder="搜索论文标题或文件名..."
        />
      </div>

      <button class="filter-btn" @click="showFilters = !showFilters">
        <Filter class="filter-icon" />
        <span>筛选</span>
      </button>
    </div>

    <div v-if="papersStore.loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else-if="papersStore.papers.length === 0 && searchQuery" class="empty-state">
      <div class="empty-icon">
        <Search class="icon" />
      </div>
      <h2>未找到匹配的论文</h2>
      <p>换个关键词试试</p>
    </div>

    <div v-else-if="papersStore.papers.length === 0" class="empty-state">
      <div class="empty-icon">
        <FileText class="icon" />
      </div>
      <h2>暂无论文</h2>
      <p>上传您的第一篇论文开始解析</p>
      <button class="upload-btn" @click="uiStore.openUploadModal()">
        <Upload class="upload-icon" />
        <span>上传论文</span>
      </button>
    </div>

    <div v-else class="papers-grid">
      <PaperCard
        v-for="paper in papersStore.papers"
        :key="paper.paper_id"
        :paper="paper"
        @view="handleViewPaper"
        @delete="handleDeletePaper"
        @reparse="handleReparse"
      />
    </div>

    <div v-if="searchQuery && papersStore.papers.length > 0" class="search-results">
      找到 {{ papersStore.papers.length }} 篇匹配的论文
    </div>

    <ConfirmModal
      v-if="dialog"
      :title="dialog.title"
      :message="dialog.message"
      :confirm-text="dialog.confirmText || '确定'"
      :cancel-text="dialog.cancelText ?? '取消'"
      :danger="dialog.danger || false"
      @confirm="handleDialogConfirm"
      @cancel="closeDialog"
    />
  </div>
</template>

<style scoped>
.home-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.title-icon {
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 10px;
}

.header-title h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 4px 0;
}

.header-title p {
  font-size: 0.9375rem;
  color: #999;
  margin: 0;
}

.anonymous-hint {
  padding: 10px 16px;
  background: #fef3c7;
  border-radius: 8px;
  font-size: 0.875rem;
  color: #d97706;
}

.page-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.search-bar {
  flex: 1;
  max-width: 400px;
  display: flex;
  align-items: center;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  padding: 0 16px;
}

.search-icon {
  width: 18px;
  height: 18px;
  color: #999;
  margin-right: 12px;
}

.search-input {
  flex: 1;
  padding: 12px 0;
  border: none;
  font-size: 0.9375rem;
  outline: none;
}

.filter-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  cursor: pointer;
  color: #666;
  font-size: 0.9375rem;
  transition: background 0.2s;
}

.filter-btn:hover {
  background: #f5f5f5;
}

.filter-icon {
  width: 18px;
  height: 18px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.loading-state p {
  color: #999;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
}

.empty-icon {
  width: 96px;
  height: 96px;
  background: #f0f0f0;
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.empty-icon .icon {
  width: 48px;
  height: 48px;
  color: #ccc;
}

.empty-state h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px 0;
}

.empty-state p {
  color: #999;
  margin: 0 0 24px 0;
}

.upload-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 32px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    transform 0.2s,
    box-shadow 0.2s;
}

.upload-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(102, 126, 234, 0.4);
}

.upload-icon {
  width: 20px;
  height: 20px;
}

.papers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
}

.search-results {
  text-align: center;
  padding: 16px;
  color: #999;
  font-size: 0.875rem;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }

  .papers-grid {
    grid-template-columns: 1fr;
  }
}
</style>
