<template>
  <div class="paper-content">
    <div v-if="loading" class="loading">
      <div class="spinner"></div>
      <p>正在加载论文...</p>
    </div>
    <div v-else-if="pdfUrl" class="pdf-viewer">
      <div class="viewer-toolbar">
        <button class="toolbar-btn" @click="toggleViewMode">
          <component :is="viewMode === 'pdf' ? FileText : FileCode" class="toolbar-icon" />
          {{ viewMode === 'pdf' ? '查看文本' : '查看PDF' }}
        </button>
        <button 
          class="toolbar-btn" 
          v-if="viewMode === 'text' && fullText"
          @click="copyFullText"
          :disabled="copying"
        >
          <component :is="copied ? Check : Copy" class="toolbar-icon" />
          {{ copied ? '已复制' : '复制全文' }}
        </button>
      </div>
      <div v-if="viewMode === 'pdf'" class="viewer-content">
        <iframe :src="pdfUrl" title="论文PDF" class="pdf-frame"></iframe>
      </div>
      <div v-else class="text-viewer">
        <div v-if="sections.length > 0" class="text-sections">
          <div 
            v-for="(section, index) in sections" 
            :key="index"
            class="section-item"
            :id="`section-${index}`"
          >
            <div class="section-header" @click="toggleSection(index)">
              <component :is="expandedSections.includes(index) ? ChevronDown : ChevronRight" class="section-icon" />
              <span class="section-title" :class="getSectionClass(section.level)">{{ section.title }}</span>
              <span v-if="section.page_number" class="section-page">第 {{ section.page_number }} 页</span>
            </div>
            <div v-if="expandedSections.includes(index)" class="section-content">
              <div 
                v-for="(paragraph, pIndex) in section.paragraphs" 
                :key="pIndex"
                class="paragraph-item"
                @click="selectParagraph($event, paragraph.text)"
                :class="{ selected: selectedParagraph === paragraph.text }"
              >
                <p>{{ paragraph.text }}</p>
                <button class="copy-btn" @click.stop="copyParagraph(paragraph.text)">
                  <Copy class="copy-icon" />
                </button>
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="fullText" class="raw-text">
          <pre>{{ fullText }}</pre>
        </div>
      </div>
    </div>
    <div v-else-if="error === 'pdf_not_found'" class="empty">
      <p>PDF 文件暂不可用</p>
      <p class="hint">可能是页面刷新后缓存丢失，请重新上传论文</p>
    </div>
    <div v-else class="empty">
      <p>{{ error || '请先上传论文' }}</p>
    </div>
    <div v-if="showToast" class="toast">{{ toastMessage }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { getPDFUrl, savePDF } from '@/utils/pdfStorage'
import { papersAPI } from '@/api'
import { FileText, FileCode, Copy, Check, ChevronDown, ChevronRight } from 'lucide-vue-next'

const props = defineProps({
  paper: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['scroll-to-section'])

const pdfUrl = ref('')
const loading = ref(true)
const error = ref(null)
const viewMode = ref('pdf')
const fullText = ref('')
const sections = ref([])
const expandedSections = ref([])
const copied = ref(false)
const copying = ref(false)
const showToast = ref(false)
const toastMessage = ref('')
const selectedParagraph = ref('')

async function fetchFromBackend(paperId) {
  try {
    const res = await papersAPI.downloadPdf(paperId)
    const blob = res.data
    savePDF(paperId, blob)
    return URL.createObjectURL(blob)
  } catch (err) {
    console.error('回源下载 PDF 失败:', err)
    return null
  }
}

async function fetchPaperDetails(paperId) {
  try {
    // api 实例装了响应拦截器 (response) => response.data，故这里 res 已是响应体本身
    const data = await papersAPI.get(paperId)
    if (data.full_text) {
      fullText.value = data.full_text
    }
    if (data.sections) {
      // 后端存储的章节结构是 { title, content, page_start, page_end }，
      // 而文本视图渲染的是 { title, level, page_number, paragraphs:[{text}] }。
      // 这里做一次归一化：content→paragraphs、page_start→page_number，
      // 同时兼容未来可能直接返回 paragraphs/page_number 的结构。
      const raw = Array.isArray(data.sections) ? data.sections : JSON.parse(data.sections)
      sections.value = (raw || []).map((s) => ({
        title: s.title,
        level: s.level,
        page_number: s.page_number ?? s.page_start,
        paragraphs: s.paragraphs ?? (s.content ? [{ text: s.content }] : []),
      }))
      expandedSections.value = sections.value.map((_, i) => i)
    }
  } catch (err) {
    console.error('获取论文详情失败:', err)
  }
}

async function loadPDF() {
  if (!props.paper.paper_id) {
    loading.value = false
    error.value = '暂无论文'
    return
  }

  loading.value = true
  error.value = null
  pdfUrl.value = ''

  try {
    await fetchPaperDetails(props.paper.paper_id)
    
    const url = await getPDFUrl(props.paper.paper_id)

    if (url) {
      pdfUrl.value = url
    } else {
      const blobUrl = await fetchFromBackend(props.paper.paper_id)
      if (blobUrl) {
        pdfUrl.value = blobUrl
      } else {
        error.value = 'pdf_not_found'
      }
    }
  } catch (err) {
    console.error('加载 PDF 失败:', err)
    error.value = '加载失败'
  } finally {
    loading.value = false
  }
}

function toggleViewMode() {
  viewMode.value = viewMode.value === 'pdf' ? 'text' : 'pdf'
}

function toggleSection(index) {
  const idx = expandedSections.value.indexOf(index)
  if (idx > -1) {
    expandedSections.value.splice(idx, 1)
  } else {
    expandedSections.value.push(index)
  }
}

function getSectionClass(level) {
  if (!level) return 'level-1'
  return `level-${Math.min(level, 4)}`
}

function selectParagraph(event, text) {
  selectedParagraph.value = text
}

async function copyParagraph(text) {
  try {
    await navigator.clipboard.writeText(text)
    showToastMessage('段落已复制')
  } catch (err) {
    console.error('复制失败:', err)
  }
}

async function copyFullText() {
  if (!fullText.value) return
  
  copying.value = true
  try {
    await navigator.clipboard.writeText(fullText.value)
    copied.value = true
    showToastMessage('全文已复制')
    setTimeout(() => {
      copied.value = false
      copying.value = false
    }, 2000)
  } catch (err) {
    console.error('复制失败:', err)
    copying.value = false
  }
}

function showToastMessage(message) {
  toastMessage.value = message
  showToast.value = true
  setTimeout(() => {
    showToast.value = false
  }, 2000)
}

function scrollToSection(pageNumber, sectionTitle) {
  viewMode.value = 'text'
  setTimeout(() => {
    // 先按章节标题定位；标题匹配不到再回退到页码定位（不再用 else-if 把兜底废掉）
    let idx = -1
    if (sectionTitle) {
      idx = sections.value.findIndex(s => (s.title || '').includes(sectionTitle))
    }
    if (idx < 0 && pageNumber) {
      idx = sections.value.findIndex(s => s.page_number === pageNumber)
    }
    if (idx > -1) {
      if (!expandedSections.value.includes(idx)) expandedSections.value.push(idx)
      setTimeout(() => {
        const el = document.getElementById(`section-${idx}`)
        if (el) el.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, 100)
}

onMounted(() => {
  loadPDF()
})

watch(
  () => props.paper.paper_id,
  () => {
    if (pdfUrl.value) {
      URL.revokeObjectURL(pdfUrl.value)
    }
    loadPDF()
  },
)

defineExpose({ scrollToSection })
</script>

<style scoped>
.paper-content {
  width: 100%;
  min-height: 800px;
  background: #f8f9fa;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 800px;
  color: #999;
}

.spinner {
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

.pdf-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.viewer-toolbar {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: white;
  border-bottom: 1px solid #e0e0e0;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #f5f7fa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.875rem;
  color: #666;
  transition: all 0.2s;
}

.toolbar-btn:hover:not(:disabled) {
  background: #667eea;
  border-color: #667eea;
  color: white;
}

.toolbar-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toolbar-icon {
  width: 16px;
  height: 16px;
}

.viewer-content {
  flex: 1;
  overflow: auto;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  min-height: 750px;
  border: none;
  background: white;
}

.text-viewer {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: white;
}

.text-sections {
  line-height: 1.8;
}

.section-item {
  margin-bottom: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.section-header:hover {
  background: #eef2f7;
}

.section-icon {
  width: 16px;
  height: 16px;
  color: #667eea;
  flex-shrink: 0;
}

.section-title {
  flex: 1;
  font-size: 0.9375rem;
  font-weight: 500;
  color: #333;
}

.section-title.level-1 {
  font-size: 1.125rem;
  font-weight: 600;
}

.section-title.level-2 {
  font-size: 1rem;
  font-weight: 600;
  padding-left: 16px;
}

.section-title.level-3 {
  font-size: 0.9375rem;
  font-weight: 500;
  padding-left: 32px;
}

.section-title.level-4 {
  font-size: 0.875rem;
  font-weight: 500;
  padding-left: 48px;
}

.section-page {
  font-size: 0.8125rem;
  color: #999;
  flex-shrink: 0;
}

.section-content {
  margin-top: 8px;
  padding-left: 32px;
}

.paragraph-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  transition: background 0.2s;
}

.paragraph-item:hover {
  background: #f0f4ff;
}

.paragraph-item.selected {
  background: #e8f0fe;
  border-left: 3px solid #667eea;
}

.paragraph-item p {
  flex: 1;
  margin: 0;
  font-size: 0.9375rem;
  color: #333;
  line-height: 1.8;
}

.copy-btn {
  opacity: 0;
  visibility: hidden;
  padding: 4px 8px;
  background: #667eea;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.paragraph-item:hover .copy-btn {
  opacity: 1;
  visibility: visible;
}

.copy-btn:hover {
  background: #764ba2;
}

.copy-icon {
  width: 14px;
  height: 14px;
  color: white;
}

.raw-text {
  padding: 20px;
}

.raw-text pre {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.8;
  color: #333;
  white-space: pre-wrap;
  word-break: break-all;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 800px;
  color: #999;
}

.hint {
  font-size: 0.85rem;
  color: #aaa;
  margin-top: 8px;
}

.toast {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 24px;
  background: #10b981;
  color: white;
  border-radius: 8px;
  font-size: 0.9375rem;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>