<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Loader2, ChevronLeft, ChevronRight, Library, Info, ArrowUp } from 'lucide-vue-next'
import { searchAPI, papersAPI } from '@/api'
import SearchResultCard from '@/components/SearchResultCard.vue'
import SearchDetailDrawer from '@/components/SearchDetailDrawer.vue'
import SearchReviewChart from '@/components/SearchReviewChart.vue'
import RecommendCard from '@/components/RecommendCard.vue'

const router = useRouter()

const query = ref('')
const loading = ref(false)
const hasSearched = ref(false)
const errorMsg = ref('')
const statusMsg = ref('')

// 加入知识库进行中：显示全屏遮罩「正在下载 PDF 并加入知识库…」（不确定态，
// PDF 由后端去 OpenAlex 下载，前端拿不到字节级进度）
const downloading = ref(false)

// 首页同款「精选推荐」（功能 C）：仅未检索时在搜索框下方展示
const recommendations = ref([])
async function loadRecommendations() {
  try {
    const res = await papersAPI.recommendations(6)
    recommendations.value = res.items || []
  } catch (err) {
    recommendations.value = []
  }
}

onMounted(loadRecommendations)

function openRecommend(paper) {
  router.push(`/papers/${paper.paper_id}`)
}

const notice = ref('')
const sources = ref([])
const chart = ref({ nodes: [], edges: [] })
const page = ref(1)
const sort = ref('citation') // 'citation'（引用量重排，默认） | 'relevance'

const selected = ref(new Set())
const adding = ref(new Set())
const added = ref(new Set())

const drawerPaper = ref(null)

const selectedAddable = computed(() =>
  sources.value.filter((p) => selected.value.has(p.id) && p.pdf_url && !added.value.has(p.id)),
)

async function runSearch(targetPage = 1) {
  if (!query.value.trim()) return
  loading.value = true
  errorMsg.value = ''
  statusMsg.value = ''
  try {
    const res = await searchAPI.query(query.value.trim(), targetPage, sort.value)
    sources.value = res.sources || []
    chart.value = res.chart || { nodes: [], edges: [] }
    page.value = res.page || targetPage
    if (targetPage <= 1) {
      notice.value = res.notice || ''
      selected.value = new Set()
    }
    hasSearched.value = true
    if (!sources.value.length) errorMsg.value = '未检索到相关论文，试试换个说法或更具体的研究问题。'
  } catch (e) {
    errorMsg.value = e?.userMessage || e?.response?.data?.detail?.error?.message || '检索失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  runSearch(1)
}

// 对话式输入框：Enter 发送，Shift+Enter 换行
function onInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (!loading.value && query.value.trim()) onSearch()
  }
}

function setSort(s) {
  if (sort.value === s) return
  sort.value = s
  if (hasSearched.value) runSearch(1)
}

function nextPage() {
  runSearch(page.value + 1)
}
function prevPage() {
  if (page.value > 1) runSearch(page.value - 1)
}

function toggleSelect(index) {
  const id = sources.value[index]?.id
  if (!id) return
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
}

function payloadOf(p) {
  return { title: p.title, pdf_url: p.pdf_url, url: p.url, field: null }
}

// 加入知识库：下载 PDF 入库成功后「新标签页」打开知识库看解析进度，本页留在搜索结果不丢失。
// 新标签是全新 App（空 store），进度由 HomePage 自身对 pending/parsing 论文的轮询驱动；
// 本页把成功篇目标记为「已加入」，卡片保留、不可重复加入。
// （后续解析/看原文流程与「直接上传」一致；详情页 PaperContent 本地无 PDF 会回后端 /download 兜底）
async function addPapers(papers) {
  const ids = papers.map((p) => p.id)
  const a = new Set(adding.value)
  ids.forEach((id) => a.add(id))
  adding.value = a
  statusMsg.value = ''
  errorMsg.value = ''
  downloading.value = true
  try {
    const res = await searchAPI.addToLibrary(papers.map(payloadOf))
    const addedList = res.added || []
    const failedList = res.failed || []

    // 成功入库：把对应搜索结果标记为「已加入」（卡片保留在本页，不再可加入）。
    // 后端按 title 标识成败，故只标记「未出现在失败列表」的篇目，避免把失败的也标成已加入。
    const okCount = addedList.length
    if (okCount) {
      const failedTitles = new Set(failedList.map((f) => f.title))
      const nextAdded = new Set(added.value)
      papers.forEach((p) => {
        if (!failedTitles.has(p.title)) nextAdded.add(p.id)
      })
      added.value = nextAdded
      // 新标签页打开知识库，本页原样保留搜索结果
      window.open('/library', '_blank')
      statusMsg.value = `${okCount} 篇已加入知识库，已在新标签页打开「知识库」查看解析进度。`
    }

    // 失败篇目：无论有无成功都在本页提示原因
    if (failedList.length) {
      const reasons = failedList.map((f) => `「${f.title}」：${f.reason}`).join('；')
      errorMsg.value = `${failedList.length} 篇未能加入 —— ${reasons}`
    }
  } catch (e) {
    errorMsg.value =
      e?.userMessage ||
      e?.response?.data?.detail?.error?.message ||
      '加入知识库失败，请确认已在设置页配置 API Key。'
  } finally {
    downloading.value = false
    const a2 = new Set(adding.value)
    ids.forEach((id) => a2.delete(id))
    adding.value = a2
  }
}

function addOne(paper) {
  addPapers([paper])
}
function addBatch() {
  if (selectedAddable.value.length) addPapers(selectedAddable.value)
}

function openDrawer(paper) {
  drawerPaper.value = paper
}
function closeDrawer() {
  drawerPaper.value = null
}
</script>

<template>
  <div class="search-page">
    <!-- 顶部大标题（渐变流光艺术字） -->
    <div v-if="!hasSearched && !loading" class="hero">
      <h1 class="hero-title">你的论文阅读助手</h1>
      <p class="hero-sub">联网检索全球真实论文，一键沉淀进知识库深读</p>
    </div>

    <!-- 检索输入：对话式输入框（类 DeepSeek），多行、右下角发送 -->
    <div class="search-bar" :class="{ 'is-hero': !hasSearched && !loading }">
      <div class="chat-box">
        <textarea
          v-model="query"
          class="chat-input"
          rows="1"
          placeholder="用一句话描述你的研究问题，如「多模态大模型的对齐方法」。Enter 检索，Shift+Enter 换行。"
          @keydown="onInputKeydown"
        ></textarea>
        <div class="chat-footer">
          <span class="chat-tip"><Search class="tip-icon" />联网检索 OpenAlex 真实论文，按被引量排序</span>
          <button class="chat-send" :disabled="loading || !query.trim()" @click="onSearch" title="检索">
            <Loader2 v-if="loading" class="send-spin" />
            <ArrowUp v-else class="send-icon" />
          </button>
        </div>
      </div>
    </div>

    <!-- 首屏：未检索时在搜索框下方展示精选推荐（有推荐则显示，否则回退引导文案） -->
    <template v-if="!hasSearched && !loading">
      <section v-if="recommendations.length" class="recommend-section">
        <h2 class="recommend-heading">🔥 精选推荐</h2>
        <div class="recommend-rows">
          <div
            v-for="r in recommendations"
            :key="r.paper_id"
            class="recommend-row"
            @click="openRecommend(r)"
          >
            <div class="row-card">
              <RecommendCard
                :paper="r"
                :reason="r.reason"
                :source="r.recommend_source"
                @view="openRecommend"
              />
            </div>
            <div class="row-abstract">
              <p v-if="r.abstract" class="abs-text">{{ r.abstract }}</p>
              <p v-else class="abs-empty">暂无摘要（论文解析完成后展示）</p>
            </div>
          </div>
        </div>
      </section>
      <div v-else class="empty-state">
        <Search class="empty-icon" />
        <p>输入研究问题，发现该方向的高被引论文与主题脉络</p>
      </div>
    </template>

    <div v-if="hasSearched" class="content">
      <!-- 左：论文列表 -->
      <div class="list-col">
        <div v-if="notice" class="notice"><Info class="ni" />{{ notice }}</div>
        <div v-if="statusMsg" class="status ok">{{ statusMsg }}</div>
        <div v-if="errorMsg" class="status err">{{ errorMsg }}</div>

        <!-- 工具栏：排序切换 + 批量加入 -->
        <div v-if="sources.length" class="toolbar">
          <div class="sort-toggle">
            <span class="sort-label">排序</span>
            <button :class="{ active: sort === 'citation' }" @click="setSort('citation')">引用量</button>
            <button :class="{ active: sort === 'relevance' }" @click="setSort('relevance')">相关度</button>
          </div>
          <button
            class="batch-btn"
            :disabled="!selectedAddable.length"
            @click="addBatch"
          >
            <Library class="bi" />批量加入知识库<span v-if="selectedAddable.length">（{{ selectedAddable.length }}）</span>
          </button>
        </div>

        <div class="result-list">
          <SearchResultCard
            v-for="(p, i) in sources"
            :key="p.id || i"
            :paper="p"
            :index="i"
            :selected="selected.has(p.id)"
            :adding="adding.has(p.id)"
            :added="added.has(p.id)"
            @toggle-select="toggleSelect"
            @add="addOne"
            @open="openDrawer"
          />
        </div>

        <div v-if="sources.length" class="pager">
          <button :disabled="page <= 1 || loading" @click="prevPage"><ChevronLeft class="pi" />上一页</button>
          <span class="page-num">第 {{ page }} 页</span>
          <button :disabled="loading" @click="nextPage">下一页<ChevronRight class="pi" /></button>
        </div>
      </div>

      <!-- 右：主题聚类图 -->
      <div class="chart-col">
        <SearchReviewChart :chart="chart" />
      </div>
    </div>

    <SearchDetailDrawer
      :paper="drawerPaper"
      :adding="drawerPaper && adding.has(drawerPaper.id)"
      :added="drawerPaper && added.has(drawerPaper.id)"
      @close="closeDrawer"
      @add="addOne"
    />

    <!-- 加入知识库遮罩：下载 PDF 入库中（不确定态），成功后在新标签页打开知识库 -->
    <div v-if="downloading" class="download-mask">
      <div class="download-card">
        <Loader2 class="download-spin" />
        <p class="download-title">正在下载 PDF 并加入知识库…</p>
        <p class="download-sub">完成后将在新标签页打开「知识库」继续解析，本页搜索结果保留</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

.search-bar {
  margin-bottom: 20px;
}

/* 顶部大标题：渐变艺术字 + 流光动画 */
.hero {
  text-align: center;
  margin: 32px 0 22px;
}

.hero-title {
  margin: 0;
  font-size: 2.9rem;
  font-weight: 800;
  letter-spacing: 1px;
  background: linear-gradient(90deg, #667eea, #764ba2, #ec4899, #667eea);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  animation: hero-flow 6s linear infinite;
}

@keyframes hero-flow {
  to {
    background-position: 300% 50%;
  }
}

.hero-sub {
  margin: 12px 0 0;
  font-size: 1rem;
  color: #9ca3af;
}

/* 首屏（未检索）时把输入框做大、加宽留白，突出 hero 感 */
.search-bar.is-hero {
  max-width: 820px;
  margin: 0 auto 32px;
}

.search-bar.is-hero .chat-input {
  min-height: 88px;
}

/* 对话式输入框（类 DeepSeek） */
.chat-box {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 20px;
  padding: 14px 16px 10px;
  box-shadow: 0 4px 18px rgba(102, 126, 234, 0.1);
  transition: box-shadow 0.2s, border-color 0.2s;
}

.chat-box:focus-within {
  border-color: #c7d2fe;
  box-shadow: 0 6px 24px rgba(102, 126, 234, 0.18);
}

.chat-input {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-size: 1.08rem;
  line-height: 1.6;
  font-family: inherit;
  color: #1f2937;
  background: transparent;
  max-height: 200px;
  min-height: 32px;
  padding: 0;
}

.chat-input::placeholder {
  color: #b0b4bb;
}

.chat-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.chat-tip {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.78rem;
  color: #9ca3af;
}

.tip-icon {
  width: 14px;
  height: 14px;
}

.chat-send {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity 0.2s;
}

.chat-send:hover:not(:disabled) {
  opacity: 0.9;
}

.chat-send:disabled {
  background: #e5e7eb;
  color: #9ca3af;
  cursor: not-allowed;
}

.send-icon {
  width: 20px;
  height: 20px;
}

.send-spin {
  width: 18px;
  height: 18px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 100px 0;
  color: #9ca3af;
}

.empty-icon {
  width: 56px;
  height: 56px;
  opacity: 0.4;
}

.content {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.list-col {
  flex: 1;
  min-width: 0;
}

.chart-col {
  width: 400px;
  flex-shrink: 0;
  position: sticky;
  top: 24px;
  height: calc(100vh - 140px);
}

.notice {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #b45309;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 0.85rem;
  margin-bottom: 12px;
}

.ni {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.status {
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 0.85rem;
  margin-bottom: 12px;
}

.status.ok {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #047857;
}

.status.err {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.sort-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sort-label {
  font-size: 0.82rem;
  color: #6b7280;
  margin-right: 4px;
}

.sort-toggle button {
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #6b7280;
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 0.82rem;
  cursor: pointer;
}

.sort-toggle button.active {
  background: #667eea;
  border-color: #667eea;
  color: #fff;
}

.batch-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #fff;
  border: 1px solid #7c3aed;
  color: #7c3aed;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.85rem;
  cursor: pointer;
}

.batch-btn:disabled {
  border-color: #e5e7eb;
  color: #9ca3af;
  cursor: not-allowed;
}

.bi {
  width: 16px;
  height: 16px;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin: 24px 0;
}

.pager button {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #374151;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
}

.pager button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-num {
  font-size: 0.88rem;
  color: #6b7280;
}

.pi {
  width: 16px;
  height: 16px;
}

/* 精选推荐区（功能 C，与首页同款栅格） */
.recommend-section {
  margin-top: 8px;
}

.recommend-heading {
  margin: 0 0 14px;
  font-size: 1.15rem;
  font-weight: 700;
  color: #1f2937;
}

/* 按行排列：左侧卡片，右侧摘要 */
.recommend-rows {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 整行是一张统一的卡：左（原推荐卡）与右（原文摘要）共用同一外框，视觉融为一体 */
.recommend-row {
  display: flex;
  align-items: stretch;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.recommend-row:hover {
  transform: translateY(-2px);
  border-color: #c7d2fe;
  box-shadow: 0 10px 26px rgba(102, 126, 234, 0.15);
}

.row-card {
  width: 288px;
  flex-shrink: 0;
}

/* 让内嵌的 RecommendCard 与右侧融为一体：去掉自身圆角/阴影/悬浮，贴合左半区，
   保留左侧学科色条（信息编码），右缘用一条淡分隔线过渡到摘要 */
.row-card :deep(.recommend-card) {
  min-height: 0;
  height: 100%;
  border-top: none;
  border-bottom: none;
  border-right: 1px solid hsla(var(--hue), 40%, 80%, 0.5);
  border-radius: 0;
  box-shadow: none;
}

.row-card :deep(.recommend-card:hover) {
  transform: none;
  box-shadow: none;
}

.row-abstract {
  flex: 1;
  min-width: 0;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  overflow: hidden;
}

.abs-text {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.8;
  color: #4b5563;
  /* 依窗口高度裁前段：多行省略，超出显示前几行 */
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.abs-empty {
  margin: 0;
  font-size: 0.88rem;
  color: #9ca3af;
}

/* 加入知识库遮罩 */
.download-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(17, 24, 39, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
}

.download-card {
  background: #fff;
  border-radius: 16px;
  padding: 32px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
}

.download-spin {
  width: 40px;
  height: 40px;
  color: #667eea;
  animation: spin 1s linear infinite;
  margin-bottom: 6px;
}

.download-title {
  font-size: 1.02rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.download-sub {
  font-size: 0.85rem;
  color: #9ca3af;
  margin: 0;
}

@media (max-width: 900px) {
  .content {
    flex-direction: column;
  }

  .chart-col {
    width: 100%;
    position: static;
    height: 360px;
  }

  .recommend-row {
    flex-direction: column;
  }

  .row-card {
    width: 100%;
  }
}
</style>
