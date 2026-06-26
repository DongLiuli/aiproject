<script setup>
import { ref, computed } from 'vue'
import { useReportsStore } from '@/stores/papers'
import {
  FileText,
  BookOpen,
  BarChart3,
  Loader2,
  Download,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Copy,
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
const expandedSections = ref(new Set())
const reportTypes = [
  { id: 'structured', name: '结构化分析', icon: BookOpen },
  { id: 'summary', name: '速读报告', icon: FileText },
  { id: 'methods', name: '方法总结', icon: BookOpen },
  { id: 'experiments', name: '实验总结', icon: BarChart3 },
]
const structuredSections = computed(() => {
  const items = []
  const info = props.paper.structured_info || {}
  if (info.research_background) {
    items.push({ id: 'research_background', title: '研究背景', content: info.research_background })
  }
  if (info.research_questions) {
    items.push({ id: 'research_questions', title: '研究问题', content: info.research_questions })
  }
  if (info.method_flow) {
    items.push({ id: 'method_flow', title: '方法流程', content: info.method_flow })
  }
  if (info.experiment_design) {
    items.push({ id: 'experiment', title: '实验设计', content: info.experiment_design })
  }
  if (info.experiment_results) {
    items.push({ id: 'results', title: '实验结果', content: info.experiment_results })
  }
  if (info.innovations) {
    items.push({ id: 'innovations', title: '创新点', content: info.innovations })
  }
  return items
})
function toggleSection(id) {
  if (expandedSections.value.has(id)) {
    expandedSections.value.delete(id)
  } else {
    expandedSections.value.add(id)
  }
  expandedSections.value = new Set(expandedSections.value)
}
async function copyContent(content) {
  try {
    await navigator.clipboard.writeText(content)
  } catch (err) {
    console.error('Copy failed:', err)
  }
}
async function generateReport(type) {
  if (generating.value) return
  generating.value = true
  activeTab.value = type
  try {
    const content = await reportsStore.generateReport(props.paperId, type)
    reportContent.value = content
  } catch (err) {
    reportContent.value = '报告生成失败，请重试'
  } finally {
    generating.value = false
  }
}
function downloadReport() {
  if (!reportContent.value) return
  const blob = new Blob([reportContent.value], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `report-${props.paperId}-${activeTab.value}.md`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="report-container">
    <div class="report-header">
      <FileText class="report-icon" />
      <h3>研读报告</h3>
      <button
        class="download-btn"
        :disabled="!reportContent"
        @click="downloadReport"
        title="下载报告"
      >
        <Download class="download-icon" />
      </button>
    </div>

    <div class="report-tabs">
      <button
        v-for="tab in reportTypes"
        :key="tab.id"
        class="tab-btn"
        :class="{ 'tab-active': activeTab === tab.id }"
        @click="tab.id === 'structured' ? (activeTab = tab.id) : generateReport(tab.id)"
      >
        <component :is="tab.icon" class="tab-icon" />
        <span>{{ tab.name }}</span>
        <Loader2 v-if="generating && activeTab === tab.id" class="tab-spinner" />
      </button>
    </div>

    <div class="report-content">
      <div v-if="activeTab === 'structured'" class="structured-content">
        <div v-if="structuredSections.length === 0" class="content-empty">
          <FileText class="empty-icon" />
          <p>暂无结构化分析数据</p>
        </div>
        <div v-for="section in structuredSections" :key="section.id" class="section-item">
          <div class="section-header" @click="toggleSection(section.id)">
            <button class="expand-btn">
              <ChevronDown v-if="expandedSections.has(section.id)" class="expand-icon" />
              <ChevronRight v-else class="expand-icon" />
            </button>
            <h4 class="section-title">{{ section.title }}</h4>
            <button class="copy-btn" @click.stop="copyContent(section.content)" title="复制内容">
              <Copy class="copy-icon" />
            </button>
          </div>
          <div v-if="expandedSections.has(section.id)" class="section-content">
            <p>{{ section.content }}</p>
          </div>
        </div>
      </div>

      <div v-else-if="!reportContent" class="content-empty">
        <FileText class="empty-icon" />
        <p>点击上方按钮生成报告</p>
      </div>

      <div v-else-if="generating" class="content-loading">
        <Loader2 class="loading-icon" />
        <span>正在生成报告...</span>
      </div>

      <div v-else class="content-body">
        <pre class="report-text">{{ reportContent }}</pre>
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

.download-btn {
  width: 36px;
  height: 36px;
  background: #f5f5f5;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.download-btn:hover:not(:disabled) {
  background: #e0e0e0;
}

.download-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.download-icon {
  width: 18px;
  height: 18px;
  color: #666;
}

.report-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #fafafa;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
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

.report-text {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.8;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
