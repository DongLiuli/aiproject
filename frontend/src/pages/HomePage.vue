<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePapersStore } from '@/stores/papers'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { FileText, Search, Filter, Upload, BookOpen, GitCompare, Network, X } from 'lucide-vue-next'
import PaperCard from '@/components/PaperCard.vue'
import RecommendCard from '@/components/RecommendCard.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import { papersAPI } from '@/api'
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

// 首页精选推荐（功能 C）
const recommendations = ref([])
async function loadRecommendations() {
  try {
    // 注意：api 响应拦截器已返回 response.data，这里直接拿 { items }
    const res = await papersAPI.recommendations(6)
    recommendations.value = res.items || []
  } catch (err) {
    // 推荐失败不影响主列表，静默降级为不展示
    recommendations.value = []
  }
}

onMounted(async () => {
  await authStore.initialize()
  await papersStore.fetchPapers()
  loadRecommendations()
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
        // 删除的论文可能正在推荐区展示（管理员推荐位/标签匹配），刷新推荐避免残留卡片点开 404
        await loadRecommendations()
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

// ==================== 选择模式：跨论文对比（A） / 知识图谱（D） ====================
// 二者共用一套卡片多选 + 底部浮动栏，互斥（进入一个自动退出另一个）
const selectMode = ref('') // '' | 'compare' | 'graph'
const selectedIds = ref([])
const compareView = ref('overall')
const viewOptions = [
  { value: 'overall', label: '综合对比' },
  { value: 'method', label: '方法对比' },
  { value: 'experiment', label: '实验对比' },
]

const completedCount = computed(
  () => papersStore.papers.filter((p) => p.parse_status === 'completed').length,
)

function enterMode(mode) {
  selectMode.value = selectMode.value === mode ? '' : mode
  selectedIds.value = []
}
function exitMode() {
  selectMode.value = ''
  selectedIds.value = []
}

function handleToggleSelect(paper) {
  const id = paper.paper_id
  const idx = selectedIds.value.indexOf(id)
  if (idx !== -1) {
    selectedIds.value.splice(idx, 1)
    return
  }
  // 对比最多 5 篇；图谱不限（越多关系越丰富）
  if (selectMode.value === 'compare' && selectedIds.value.length >= 5) {
    openDialog({ title: '数量超限', message: '最多选择 5 篇论文进行对比', cancelText: '' })
    return
  }
  selectedIds.value.push(id)
}

function selectAllCompleted() {
  selectedIds.value = papersStore.papers
    .filter((p) => p.parse_status === 'completed')
    .map((p) => p.paper_id)
}

function startCompare() {
  if (selectedIds.value.length < 2) {
    openDialog({ title: '选择不足', message: '请至少选择 2 篇论文进行对比', cancelText: '' })
    return
  }
  router.push({
    name: 'compare',
    query: { ids: selectedIds.value.join(','), view: compareView.value },
  })
}

function startGraph() {
  if (selectedIds.value.length < 1) {
    openDialog({ title: '选择不足', message: '请至少选择 1 篇论文生成图谱', cancelText: '' })
    return
  }
  router.push({ name: 'graph', query: { ids: selectedIds.value.join(',') } })
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

    <section v-if="recommendations.length" class="recommend-section">
      <h2 class="recommend-heading">🔥 精选推荐</h2>
      <div class="recommend-grid">
        <RecommendCard
          v-for="r in recommendations"
          :key="r.paper_id"
          :paper="r"
          :reason="r.reason"
          :source="r.recommend_source"
          @view="handleViewPaper"
        />
      </div>
    </section>

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

      <button
        class="filter-btn compare-toggle"
        :class="{ active: selectMode === 'compare' }"
        @click="enterMode('compare')"
        :disabled="completedCount < 2"
        :title="completedCount < 2 ? '至少需要 2 篇已解析论文' : ''"
      >
        <GitCompare class="filter-icon" />
        <span>{{ selectMode === 'compare' ? '退出对比' : '对比' }}</span>
      </button>

      <button
        class="filter-btn graph-entry"
        :class="{ active: selectMode === 'graph' }"
        @click="enterMode('graph')"
        :disabled="completedCount < 1"
        :title="completedCount < 1 ? '至少需要 1 篇已解析论文' : '选择论文生成知识图谱'"
      >
        <Network class="filter-icon" />
        <span>{{ selectMode === 'graph' ? '退出图谱' : '知识图谱' }}</span>
      </button>
    </div>

    <div v-if="selectMode === 'compare'" class="compare-hint">
      对比模式：勾选 2~5 篇已解析论文，然后点击底部「开始对比」
    </div>
    <div v-else-if="selectMode === 'graph'" class="compare-hint">
      图谱模式：勾选参与构图的已解析论文（可「全选」），然后点击底部「生成图谱」
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
        :selectable="!!selectMode"
        :selected="selectedIds.includes(paper.paper_id)"
        @view="handleViewPaper"
        @delete="handleDeletePaper"
        @reparse="handleReparse"
        @toggle-select="handleToggleSelect"
      />
    </div>

    <!-- 对比模式浮动栏 -->
    <div v-if="selectMode === 'compare'" class="compare-bar">
      <div class="compare-bar-info">
        <GitCompare class="compare-bar-icon" />
        <span>已选 <strong>{{ selectedIds.length }}</strong> / 5 篇</span>
      </div>
      <div class="compare-bar-actions">
        <select v-model="compareView" class="compare-view-select">
          <option v-for="opt in viewOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <button class="compare-start-btn" :disabled="selectedIds.length < 2" @click="startCompare">
          开始对比
        </button>
        <button class="compare-close-btn" @click="exitMode" title="退出对比">
          <X class="compare-close-icon" />
        </button>
      </div>
    </div>

    <!-- 图谱模式浮动栏 -->
    <div v-else-if="selectMode === 'graph'" class="compare-bar">
      <div class="compare-bar-info">
        <Network class="compare-bar-icon" />
        <span>已选 <strong>{{ selectedIds.length }}</strong> 篇</span>
      </div>
      <div class="compare-bar-actions">
        <button class="compare-view-select" @click="selectAllCompleted">全选</button>
        <button class="compare-start-btn" :disabled="selectedIds.length < 1" @click="startGraph">
          生成图谱
        </button>
        <button class="compare-close-btn" @click="exitMode" title="退出图谱">
          <X class="compare-close-icon" />
        </button>
      </div>
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

.filter-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.compare-toggle.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-color: transparent;
}

.graph-entry:hover {
  border-color: #667eea;
  color: #4f46e5;
}

.compare-hint {
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #eef2ff;
  color: #4f46e5;
  border-radius: 8px;
  font-size: 0.875rem;
}

.compare-bar {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 20px;
  background: white;
  border-radius: 14px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.18);
}

.compare-bar-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #333;
  font-size: 0.9375rem;
}

.compare-bar-info strong {
  color: #667eea;
}

.compare-bar-icon {
  width: 18px;
  height: 18px;
  color: #667eea;
}

.compare-bar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.compare-view-select {
  padding: 8px 12px;
  background: white;
  color: #333;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.875rem;
  cursor: pointer;
  outline: none;
}

.compare-start-btn {
  padding: 8px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
}

.compare-start-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.compare-close-btn {
  width: 36px;
  height: 36px;
  background: #f5f5f5;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.compare-close-btn:hover {
  background: #e0e0e0;
}

.compare-close-icon {
  width: 18px;
  height: 18px;
  color: #666;
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

/* 精选推荐区（功能 C） */
.recommend-section {
  margin-bottom: 28px;
}
.recommend-heading {
  margin: 0 0 14px;
  font-size: 1.15rem;
  font-weight: 700;
  color: #1f2937;
}
.recommend-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }

  .papers-grid {
    grid-template-columns: 1fr;
  }

  .recommend-grid {
    grid-template-columns: 1fr;
  }
}
</style>
