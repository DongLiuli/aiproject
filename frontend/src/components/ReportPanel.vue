<script setup>
import { ref, computed, onMounted } from 'vue'
import { useReportsStore } from '@/stores/papers'
import { marked } from 'marked'
import {
  FileText,
  BookOpen,
  BarChart3,
  Loader2,
  Download,
  Copy,
  Check,
  RefreshCw,
} from 'lucide-vue-next'

const props = defineProps({
  paperId: {
    type: String,
    required: true,
  },
  paper: {
    type: Object,
    default: () => ({}),
  },
})

const reportsStore = useReportsStore()
const activeTab = ref('structured')
const generating = ref(false)
const reportContent = ref('')
const copied = ref(false)

const reportTypes = [
  { id: 'structured', name: '结构化分析', icon: BookOpen },
  { id: 'quick', name: '速读报告', icon: FileText },
  { id: 'method', name: '方法总结', icon: BookOpen },
  { id: 'experiment', name: '实验总结', icon: BarChart3 },
]

const renderedContent = computed(() => {
  if (!reportContent.value) return ''
  return marked(reportContent.value)
})

const structuredMarkdown = computed(() => {
  const info = props.paper.structured_info
  if (!info) return ''

  let parsedInfo = info
  if (typeof info === 'string') {
    try {
      parsedInfo = JSON.parse(info)
    } catch {
      return ''
    }
  }

  let md = ''

  if (parsedInfo.research_background) {
    md += `## 研究背景\n\n${parsedInfo.research_background}\n\n`
  }
  if (parsedInfo.research_questions) {
    md += `## 研究问题\n\n${parsedInfo.research_questions}\n\n`
  }
  if (parsedInfo.method_flow) {
    md += `## 方法流程\n\n${parsedInfo.method_flow}\n\n`
  }
  if (parsedInfo.model_algorithm) {
    md += `## 模型算法\n\n${parsedInfo.model_algorithm}\n\n`
  }
  if (parsedInfo.dataset_info) {
    md += `## 数据集信息\n\n${parsedInfo.dataset_info}\n\n`
  }
  if (parsedInfo.experiment_results) {
    md += `## 实验结果\n\n${parsedInfo.experiment_results}\n\n`
  }
  if (parsedInfo.innovations) {
    md += `## 创新点\n\n`
    const innovations = Array.isArray(parsedInfo.innovations)
      ? parsedInfo.innovations
      : [parsedInfo.innovations]
    innovations.forEach((item) => {
      md += `- ${item}\n`
    })
    md += '\n'
  }
  if (parsedInfo.limitations) {
    md += `## 局限性\n\n`
    const limitations = Array.isArray(parsedInfo.limitations)
      ? parsedInfo.limitations
      : [parsedInfo.limitations]
    limitations.forEach((item) => {
      md += `- ${item}\n`
    })
    md += '\n'
  }
  if (parsedInfo.future_work) {
    md += `## 未来工作\n\n${parsedInfo.future_work}\n\n`
  }

  return md
})

const structuredRendered = computed(() => {
  return marked(structuredMarkdown.value)
})

const currentReportContent = computed(() => {
  if (activeTab.value === 'structured') return ''
  return reportsStore.getReport(props.paperId, activeTab.value) || ''
})

const currentRendered = computed(() => {
  if (!currentReportContent.value) return ''
  return marked(currentReportContent.value)
})

async function copyContent(content) {
  if (!content) return
  try {
    await navigator.clipboard.writeText(content)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (err) {
    console.error('Copy failed:', err)
  }
}

async function generateReport(type) {
  if (generating.value) return

  if (!props.paper.structured_info) {
    reportContent.value = '论文尚未完成解析，请先等待解析完成或点击"重新解析"按钮'
    return
  }

  generating.value = true
  activeTab.value = type
  try {
    const content = await reportsStore.generateReport(props.paperId, type)
    reportContent.value = content
  } catch (err) {
    const errorMsg = err.response?.data?.error?.message || '报告生成失败，请重试'
    reportContent.value = errorMsg
  } finally {
    generating.value = false
  }
}

function switchTab(type) {
  activeTab.value = type
  if (type !== 'structured') {
    reportContent.value = currentReportContent.value
  }
}

function downloadReport() {
  const content =
    activeTab.value === 'structured' ? structuredMarkdown.value : currentReportContent.value
  if (!content) return
  const blob = new Blob([content], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const reportName = reportTypes.find((t) => t.id === activeTab.value)?.name || '报告'
  a.download = `${reportName}-${props.paperId.substring(0, 8)}.md`
  a.click()
  URL.revokeObjectURL(url)
}

async function loadSavedReports() {
  if (!props.paperId) return
  try {
    await reportsStore.getReports(props.paperId)
    if (activeTab.value !== 'structured') {
      reportContent.value = currentReportContent.value
    }
  } catch (err) {
    console.error('Failed to load saved reports:', err)
  }
}

onMounted(() => {
  loadSavedReports()
})
</script>

<template>
  <div class="report-container">
    <div class="report-header">
      <FileText class="report-icon" />
      <h3>研读报告</h3>
      <div class="header-actions">
        <button
          class="action-btn"
          :disabled="!currentReportContent && !structuredMarkdown"
          @click="
            copyContent(activeTab === 'structured' ? structuredMarkdown : currentReportContent)
          "
          title="复制报告"
        >
          <Check v-if="copied" class="action-icon" />
          <Copy v-else class="action-icon" />
          <span>{{ copied ? '已复制' : '复制' }}</span>
        </button>
        <button
          class="action-btn download"
          :disabled="!currentReportContent && !structuredMarkdown"
          @click="downloadReport"
          title="下载报告"
        >
          <Download class="action-icon" />
          <span>下载</span>
        </button>
      </div>
    </div>

    <div class="report-tabs">
      <button
        v-for="tab in reportTypes"
        :key="tab.id"
        class="tab-btn"
        :class="{ 'tab-active': activeTab === tab.id }"
        @click="switchTab(tab.id)"
      >
        <component :is="tab.icon" class="tab-icon" />
        <span>{{ tab.name }}</span>
        <Loader2 v-if="generating && activeTab === tab.id" class="tab-spinner" />
      </button>
    </div>

    <div class="report-content">
      <div v-if="generating" class="content-loading">
        <Loader2 class="loading-icon" />
        <span>正在生成报告...</span>
      </div>

      <div v-else-if="activeTab === 'structured'" class="structured-content">
        <div v-if="!paper.structured_info" class="content-empty">
          <FileText class="empty-icon" />
          <p>暂无结构化分析数据</p>
        </div>
        <div v-else class="markdown-preview" v-html="structuredRendered"></div>
      </div>

      <div v-else-if="!currentReportContent" class="content-empty">
        <FileText class="empty-icon" />
        <p>暂无报告</p>
        <button class="generate-btn" @click="generateReport(activeTab)">
          <RefreshCw class="btn-icon" />
          <span>生成报告</span>
        </button>
      </div>

      <div v-else class="content-body">
        <div class="body-header">
          <button class="regenerate-btn" @click="generateReport(activeTab)">
            <RefreshCw class="btn-icon" />
            <span>重新生成</span>
          </button>
        </div>
        <div class="markdown-preview" v-html="currentRendered"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.report-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.report-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
}

.report-icon {
  width: 20px;
  height: 20px;
  color: #764ba2;
}

.report-header h3 {
  flex: 1;
  font-size: 1rem;
  font-weight: 600;
  color: #333;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #f5f5f5;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.8rem;
  color: #666;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: #e0e0e0;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.download {
  background: #667eea;
  color: white;
}

.action-btn.download:hover:not(:disabled) {
  background: #5a6fd6;
}

.action-icon {
  width: 16px;
  height: 16px;
}

.report-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #fafafa;
  flex-wrap: wrap;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.875rem;
  color: #666;
  transition: all 0.2s;
}

.tab-btn:hover {
  border-color: #667eea;
  color: #667eea;
}

.tab-active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
  color: white;
}

.tab-icon {
  width: 16px;
  height: 16px;
}

.tab-spinner {
  width: 16px;
  height: 16px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.report-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.content-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.generate-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 500;
  transition: transform 0.2s;
}

.generate-btn:hover {
  transform: translateY(-2px);
}

.btn-icon {
  width: 18px;
  height: 18px;
}

.content-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #667eea;
}

.loading-icon {
  width: 32px;
  height: 32px;
  margin-bottom: 12px;
  animation: spin 1s linear infinite;
}

.content-body {
  padding: 16px;
  background: #fafafa;
  border-radius: 10px;
}

.body-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.regenerate-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: white;
  border: 1px solid #667eea;
  border-radius: 8px;
  color: #667eea;
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.2s;
}

.regenerate-btn:hover {
  background: #f5f7ff;
}

.markdown-preview {
  font-size: 0.9rem;
  line-height: 1.8;
  color: #333;
}

.markdown-preview h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid #667eea;
}

.markdown-preview h2 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #333;
  margin: 24px 0 12px 0;
  padding-left: 10px;
  border-left: 4px solid #667eea;
}

.markdown-preview h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #444;
  margin: 20px 0 10px 0;
}

.markdown-preview p {
  margin: 10px 0;
}

.markdown-preview ul,
.markdown-preview ol {
  margin: 10px 0;
  padding-left: 24px;
}

.markdown-preview li {
  margin: 6px 0;
}

.markdown-preview strong {
  font-weight: 600;
  color: #1a1a1a;
}

.markdown-preview em {
  font-style: italic;
}

.markdown-preview code {
  background: #e8f4fd;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85rem;
  font-family: 'Monaco', 'Menlo', monospace;
}

.markdown-preview pre {
  background: #1a1a2e;
  color: #e4e4e7;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-preview pre code {
  background: none;
  padding: 0;
  color: inherit;
  font-size: 0.85rem;
}

.markdown-preview table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
  font-size: 0.85rem;
}

.markdown-preview th,
.markdown-preview td {
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  text-align: left;
}

.markdown-preview th {
  background: #f5f5f5;
  font-weight: 600;
  color: #333;
}

.markdown-preview tr:nth-child(even) {
  background: #fafafa;
}

.markdown-preview a {
  color: #667eea;
  text-decoration: none;
}

.markdown-preview a:hover {
  text-decoration: underline;
}

.markdown-preview blockquote {
  border-left: 4px solid #667eea;
  padding: 10px 16px;
  margin: 12px 0;
  background: #f5f7ff;
  color: #555;
}

.markdown-preview hr {
  border: none;
  border-top: 1px solid #e0e0e0;
  margin: 24px 0;
}
</style>
