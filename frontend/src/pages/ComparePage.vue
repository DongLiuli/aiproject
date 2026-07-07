<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { reportsAPI } from '@/api'
import {
  ArrowLeft,
  GitCompare,
  Loader2,
  Copy,
  Check,
  Download,
  RefreshCw,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const viewOptions = [
  { value: 'overall', label: '综合对比' },
  { value: 'method', label: '方法对比' },
  { value: 'experiment', label: '实验对比' },
]

const paperIds = ref([])
const currentView = ref('overall')
const table = ref(null)
const summary = ref('')
const generating = ref(false)
const errorMsg = ref('')

// 视角缓存：已生成过的视角切回时秒出，不再重复检索+调 LLM
const viewCache = ref({})
// 单元格展开状态（长内容折叠）
const expandedCells = ref(new Set())
const copied = ref(false)
const CLAMP_THRESHOLD = 120

const renderedSummary = computed(() => (summary.value ? marked(summary.value) : ''))

async function runCompare(view) {
  currentView.value = view
  table.value = null
  summary.value = ''
  errorMsg.value = ''
  expandedCells.value = new Set()
  generating.value = true
  try {
    await reportsAPI.compareStream(paperIds.value, view, {
      onTable: (t) => {
        table.value = t
      },
      onDelta: (content) => {
        summary.value = content
      },
    })
    // 成功后缓存该视角结果
    viewCache.value[view] = { table: table.value, summary: summary.value }
  } catch (err) {
    errorMsg.value = err.userMessage || '对比生成失败，请重试'
  } finally {
    generating.value = false
  }
}

// 优先命中缓存，未命中才真正生成
function loadView(view) {
  const cached = viewCache.value[view]
  if (cached) {
    currentView.value = view
    table.value = cached.table
    summary.value = cached.summary
    errorMsg.value = ''
    expandedCells.value = new Set()
    return
  }
  runCompare(view)
}

function switchView(view) {
  if (view === currentView.value || generating.value) return
  router.replace({ name: 'compare', query: { ids: paperIds.value.join(','), view } })
  loadView(view)
}

// 失败重试：无需退回重选，直接对当前视角重新生成
function retry() {
  runCompare(currentView.value)
}

// ---- 长单元格折叠 ----
function cellKey(rowKey, i) {
  return `${rowKey}-${i}`
}
function isExpanded(rowKey, i) {
  return expandedCells.value.has(cellKey(rowKey, i))
}
function toggleCell(rowKey, i) {
  const k = cellKey(rowKey, i)
  const next = new Set(expandedCells.value)
  next.has(k) ? next.delete(k) : next.add(k)
  expandedCells.value = next
}

// ---- 复制 / 导出 ----
async function copySummary() {
  if (!summary.value) return
  try {
    await navigator.clipboard.writeText(summary.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch (err) {
    console.error('复制失败:', err)
  }
}

function tableToMarkdown() {
  if (!table.value) return ''
  const t = table.value
  const header = ['维度', ...t.papers.map((p, i) => `论文${String.fromCharCode(65 + i)}：${p.title}`)]
  const esc = (v) => (v || '').replace(/\|/g, '\\|').replace(/\n/g, '<br>')
  let md = `| ${header.map(esc).join(' | ')} |\n| ${header.map(() => '---').join(' | ')} |\n`
  for (const row of t.rows) {
    md += `| ${[row.label, ...row.values].map(esc).join(' | ')} |\n`
  }
  return md
}

function downloadComparison() {
  if (!table.value) return
  const title = viewOptions.find((o) => o.value === currentView.value)?.label || '对比'
  const md =
    `# 跨论文对比 · ${title}\n\n## 对比表格\n\n${tableToMarkdown()}\n\n## 综述小结\n\n${summary.value || ''}\n`
  const blob = new Blob([md], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `跨论文对比-${title}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function goBack() {
  router.push({ name: 'library' })
}

onMounted(() => {
  const ids = (route.query.ids || '').split(',').filter(Boolean)
  const view = viewOptions.some((o) => o.value === route.query.view)
    ? route.query.view
    : 'overall'
  paperIds.value = ids
  if (ids.length < 2) {
    errorMsg.value = '对比至少需要 2 篇论文，请返回重新选择'
    return
  }
  loadView(view)
})
</script>

<template>
  <div class="compare-page">
    <div class="compare-header">
      <button class="back-btn" @click="goBack">
        <ArrowLeft class="back-icon" />
        <span>返回文献库</span>
      </button>
      <div class="header-title">
        <GitCompare class="title-icon" />
        <h1>跨论文对比</h1>
        <span v-if="table" class="paper-count">共 {{ table.papers.length }} 篇</span>
      </div>
      <div class="toolbar">
        <div class="view-tabs">
          <button
            v-for="opt in viewOptions"
            :key="opt.value"
            class="view-tab"
            :class="{ active: currentView === opt.value }"
            :disabled="generating"
            @click="switchView(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>

        <div class="tool-actions">
          <button
            class="tool-btn"
            :disabled="!summary || generating"
            @click="copySummary"
            title="复制综述"
          >
            <Check v-if="copied" class="tool-icon" />
            <Copy v-else class="tool-icon" />
            <span>{{ copied ? '已复制' : '复制综述' }}</span>
          </button>
          <button
            class="tool-btn"
            :disabled="!table || generating"
            @click="downloadComparison"
            title="导出为 Markdown"
          >
            <Download class="tool-icon" />
            <span>导出</span>
          </button>
        </div>
      </div>
    </div>

    <div v-if="errorMsg" class="error-banner">
      <span>{{ errorMsg }}</span>
      <button v-if="paperIds.length >= 2" class="retry-btn" @click="retry">
        <RefreshCw class="retry-icon" />
        <span>重新生成</span>
      </button>
    </div>

    <!-- 对比表格：首帧即渲染，首列冻结、横向滚动 -->
    <div v-if="table" class="table-wrapper">
      <table class="compare-table">
        <thead>
          <tr>
            <th class="dim-col">维度</th>
            <th v-for="(p, i) in table.papers" :key="p.paper_id" class="paper-col">
              <span class="paper-tag">论文{{ String.fromCharCode(65 + i) }}</span>
              <span class="paper-name" :title="p.title">{{ p.title }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in table.rows" :key="row.key">
            <td class="dim-col dim-label">{{ row.label }}</td>
            <td v-for="(val, i) in row.values" :key="i" class="cell">
              <div
                class="cell-content"
                :class="{ clamped: val.length > CLAMP_THRESHOLD && !isExpanded(row.key, i) }"
              >
                {{ val }}
              </div>
              <button
                v-if="val.length > CLAMP_THRESHOLD"
                class="cell-toggle"
                @click="toggleCell(row.key, i)"
              >
                {{ isExpanded(row.key, i) ? '收起' : '展开' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!errorMsg" class="table-skeleton">
      <div class="skeleton-line" v-for="n in 5" :key="n"></div>
    </div>

    <!-- 综述小结：SSE 流式渲染 -->
    <div class="summary-section">
      <div class="summary-title">
        <span>📝 综述小结</span>
        <span v-if="generating" class="streaming-badge">
          <Loader2 class="spin-icon" /> 生成中…
        </span>
      </div>

      <div v-if="renderedSummary" class="summary-content" v-html="renderedSummary"></div>
      <div v-else-if="generating && !errorMsg" class="summary-skeleton">
        <div class="skeleton-line" v-for="n in 4" :key="n"></div>
      </div>
      <div v-else-if="!errorMsg" class="summary-empty">暂无综述内容</div>
    </div>
  </div>
</template>

<style scoped>
.compare-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.compare-header {
  margin-bottom: 20px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: #667eea;
  font-size: 0.9375rem;
  cursor: pointer;
  padding: 0;
  margin-bottom: 12px;
}

.back-icon {
  width: 18px;
  height: 18px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.title-icon {
  width: 32px;
  height: 32px;
  color: #667eea;
}

.header-title h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0;
}

.paper-count {
  font-size: 0.875rem;
  color: #999;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.view-tabs {
  display: flex;
  gap: 8px;
}

.tool-actions {
  display: flex;
  gap: 8px;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 0.875rem;
  color: #555;
  cursor: pointer;
  transition: all 0.2s;
}

.tool-btn:hover:not(:disabled) {
  background: #f5f5f5;
}

.tool-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tool-icon {
  width: 15px;
  height: 15px;
}

.view-tab {
  padding: 8px 18px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 0.9375rem;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
}

.view-tab:hover:not(:disabled) {
  background: #f5f5f5;
}

.view-tab.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-color: transparent;
}

.view-tab:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  background: #fef2f2;
  color: #dc2626;
  border-radius: 10px;
  border-left: 3px solid #dc2626;
  margin-bottom: 20px;
}

.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: white;
  border: 1px solid #dc2626;
  border-radius: 8px;
  color: #dc2626;
  font-size: 0.875rem;
  cursor: pointer;
  flex-shrink: 0;
}

.retry-btn:hover {
  background: #dc2626;
  color: white;
}

.retry-icon {
  width: 14px;
  height: 14px;
}

.table-wrapper {
  overflow-x: auto;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-bottom: 24px;
}

.compare-table {
  border-collapse: collapse;
  width: 100%;
  min-width: 600px;
}

.compare-table th,
.compare-table td {
  border: 1px solid #eee;
  padding: 12px 14px;
  text-align: left;
  vertical-align: top;
  font-size: 0.875rem;
}

.dim-col {
  position: sticky;
  left: 0;
  z-index: 2;
  background: #f8fafc;
  min-width: 96px;
  width: 96px;
}

.dim-label {
  font-weight: 600;
  color: #475569;
}

.paper-col {
  background: #f8fafc;
  min-width: 220px;
}

.paper-tag {
  display: inline-block;
  background: #eef2ff;
  color: #4f46e5;
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 6px;
  margin-right: 6px;
}

.paper-name {
  font-weight: 600;
  color: #1a1a1a;
}

.cell {
  color: #444;
  line-height: 1.6;
}

.cell-content {
  white-space: pre-wrap;
}

.cell-content.clamped {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.cell-toggle {
  margin-top: 4px;
  padding: 0;
  background: none;
  border: none;
  color: #667eea;
  font-size: 0.8125rem;
  cursor: pointer;
}

.cell-toggle:hover {
  text-decoration: underline;
}

.table-skeleton,
.summary-skeleton {
  padding: 20px;
}

.skeleton-line {
  height: 16px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e6e6e6 37%, #f0f0f0 63%);
  background-size: 400% 100%;
  border-radius: 6px;
  margin-bottom: 12px;
  animation: shimmer 1.4s ease infinite;
}

@keyframes shimmer {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}

.summary-section {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 24px;
}

.summary-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 1.125rem;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 16px;
}

.streaming-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.8125rem;
  font-weight: 400;
  color: #667eea;
}

.spin-icon {
  width: 14px;
  height: 14px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.summary-empty {
  color: #999;
  font-size: 0.9375rem;
}

.summary-content {
  line-height: 1.8;
  color: #333;
}

.summary-content :deep(h1) {
  font-size: 1.5rem;
  margin: 16px 0 12px;
}

.summary-content :deep(h2) {
  font-size: 1.25rem;
  margin: 16px 0 10px;
}

.summary-content :deep(h3) {
  font-size: 1.0625rem;
  margin: 12px 0 8px;
}

.summary-content :deep(p) {
  margin: 8px 0;
}

.summary-content :deep(ul),
.summary-content :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.summary-content :deep(table) {
  border-collapse: collapse;
  margin: 12px 0;
}

.summary-content :deep(th),
.summary-content :deep(td) {
  border: 1px solid #e0e0e0;
  padding: 8px 12px;
}
</style>
