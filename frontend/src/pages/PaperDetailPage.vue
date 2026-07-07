<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePapersStore } from '@/stores/papers'
import {
  ArrowLeft,
  FileText,
  Clock,
  Users,
  Calendar,
  MessageSquare,
  FileOutput,
} from 'lucide-vue-next'
import PaperContent from '@/components/PaperContent.vue'
import QAInterface from '@/components/QAInterface.vue'
import ReportPanel from '@/components/ReportPanel.vue'
const route = useRoute()
const router = useRouter()
const papersStore = usePapersStore()
// 右栏在「智能问答 / 研读报告」间切换，默认问答；左栏 PaperContent 常显
const rightTab = ref('qa')
const paperId = computed(() => route.params.id)
const paper = computed(() => papersStore.currentPaper)
const paperContentRef = ref(null)

function handleScrollToSection(pageNumber, sectionTitle) {
  if (paperContentRef.value) {
    paperContentRef.value.scrollToSection(pageNumber, sectionTitle)
  }
}

onMounted(async () => {
  if (!paperId.value) return
  try {
    await papersStore.getPaper(paperId.value)
  } catch (err) {
    console.error('Failed to load paper:', err)
  }
})
function goBack() {
  router.push('/library')
}
const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}
const formatSize = (bytes) => {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}
</script>

<template>
  <div class="detail-page">
    <div v-if="!paper" class="loading-state">
      <div class="loading-spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else class="paper-detail">
      <div class="detail-header">
        <button class="back-btn" @click="goBack">
          <ArrowLeft class="back-icon" />
          <span>返回</span>
        </button>
      </div>

      <div class="paper-header">
        <div class="paper-icon">
          <FileText class="icon" />
        </div>
        <div class="paper-meta">
          <h1 class="paper-title">{{ paper.title || paper.file_name }}</h1>
          <div class="meta-info">
            <span v-if="paper.authors" class="meta-item">
              <Users class="meta-icon" />
              {{ paper.authors }}
            </span>
            <span class="meta-item">
              <Calendar class="meta-icon" />
              {{ formatDate(paper.upload_time) }}
            </span>
            <span class="meta-item">
              <Clock class="meta-icon" />
              {{ formatSize(paper.file_size) }}
            </span>
          </div>
        </div>
        <span class="status-badge" :class="`status-${paper.parse_status}`">
          {{
            paper.parse_status === 'uploaded'
              ? '已上传'
              : paper.parse_status === 'parsing'
                ? '解析中'
                : paper.parse_status === 'completed'
                  ? '已完成'
                  : '失败'
          }}
        </span>
      </div>

      <div class="detail-content">
        <div class="left-pane">
          <PaperContent ref="paperContentRef" :paper="paper" />
        </div>

        <div class="right-pane">
          <div class="pane-switch">
            <button
              class="switch-btn"
              :class="{ 'switch-active': rightTab === 'qa' }"
              @click="rightTab = 'qa'"
            >
              <MessageSquare class="switch-icon" />
              <span>智能问答</span>
            </button>
            <button
              class="switch-btn"
              :class="{ 'switch-active': rightTab === 'report' }"
              @click="rightTab = 'report'"
            >
              <FileOutput class="switch-icon" />
              <span>研读报告</span>
            </button>
          </div>

          <QAInterface
            v-show="rightTab === 'qa'"
            class="pane-body"
            :paper-id="paperId"
            :parse-status="paper.parse_status"
            @scroll-to-section="handleScrollToSection"
          />
          <ReportPanel
            v-show="rightTab === 'report'"
            class="pane-body"
            :paper-id="paperId"
            :paper="paper"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-page {
  min-height: 100vh;
  background: #f5f7fa;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
}

.loading-spinner {
  width: 48px;
  height: 48px;
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

.paper-detail {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 16px 24px; /* 👈 减小顶部内边距（原来是 24px） */
  box-sizing: border-box;
}

.detail-header {
  margin-bottom: 8px; /* 👈 减小底部间距（原来是 16px） */
  flex-shrink: 0;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: #667eea;
  font-size: 0.85rem; /* 👈 稍微减小字体（原来是 0.9375rem） */
  cursor: pointer;
  transition: color 0.2s;
  padding: 4px 0; /* 👈 减少按钮自身占用的空间 */
}

.back-btn:hover {
  color: #764ba2;
}

.back-icon {
  width: 16px; /* 👈 减小图标（原来是 18px） */
  height: 16px;
}

.paper-header {
  display: flex;
  gap: 16px; /* 👈 减小间距（原来是 20px） */
  padding: 14px 20px; /* 👈 减小内边距（原来是 24px） */
  background: white;
  border-radius: 12px; /* 👈 稍微减小圆角（原来是 16px） */
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-bottom: 12px; /* 👈 减小底部间距（原来是 16px） */
  flex-shrink: 0;
}

.paper-icon {
  width: 48px; /* 👈 减小图标容器（原来是 64px） */
  height: 48px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px; /* 👈 减小圆角（原来是 16px） */
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon {
  width: 24px; /* 👈 减小图标（原来是 32px） */
  height: 24px;
  color: white;
}

.paper-meta {
  flex: 1;
}

.paper-title {
  font-size: 1.2rem; /* 👈 减小标题字体（原来是 1.5rem） */
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 8px 0; /* 👈 减小底部间距（原来是 16px） */
}

.meta-info {
  display: flex;
  flex-wrap: wrap;
  gap: 12px; /* 👈 减小间距（原来是 20px） */
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px; /* 👈 减小间距（原来是 8px） */
  font-size: 0.85rem; /* 👈 减小字体（原来是 0.9375rem） */
  color: #666;
}

.meta-icon {
  width: 14px; /* 👈 减小图标（原来是 18px） */
  height: 14px;
}

.status-badge {
  padding: 4px 12px; /* 👈 减小内边距（原来是 8px 16px） */
  border-radius: 16px; /* 👈 减小圆角（原来是 20px） */
  font-size: 0.8rem; /* 👈 减小字体（原来是 0.875rem） */
  font-weight: 500;
  flex-shrink: 0;
  align-self: center; /* 👈 垂直居中 */
}

.status-uploaded {
  background: #fef3c7;
  color: #d97706;
}

.status-parsing {
  background: #dbeafe;
  color: #2563eb;
}

.status-completed {
  background: #dcfce7;
  color: #16a34a;
}

.status-failed {
  background: #fee2e2;
  color: #dc2626;
}

.detail-content {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
}

.left-pane {
  flex: 1.2;
  min-width: 0;
  overflow: auto;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.right-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pane-switch {
  display: flex;
  gap: 8px; /* 👈 减小间距（原来是 12px） */
  flex-shrink: 0;
}

.switch-btn {
  display: flex;
  align-items: center;
  gap: 6px; /* 👈 减小间距（原来是 8px） */
  padding: 8px 16px; /* 👈 减小内边距（原来是 12px 20px） */
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 10px; /* 👈 减小圆角（原来是 12px） */
  cursor: pointer;
  font-size: 0.85rem; /* 👈 减小字体（原来是 0.9375rem） */
  font-weight: 500;
  color: #666;
  transition: all 0.2s;
}

.switch-btn:hover {
  border-color: #667eea;
  color: #667eea;
}

.switch-active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
  color: white;
}

.switch-icon {
  width: 16px; /* 👈 减小图标（原来是 18px） */
  height: 16px;
}

.pane-body {
  flex: 1;
  min-height: 0;
}

@media (max-width: 900px) {
  .paper-detail {
    height: auto;
    min-height: 100vh;
  }

  .detail-content {
    flex-direction: column;
  }

  .left-pane {
    height: 70vh;
    flex: none;
  }

  .right-pane {
    height: 80vh;
    flex: none;
  }
}

@media (max-width: 768px) {
  .paper-header {
    flex-direction: column;
  }

  .paper-title {
    font-size: 1.1rem;
  }

  .meta-info {
    flex-direction: column;
    gap: 8px;
  }

  .status-badge {
    align-self: flex-start;
  }
}
</style>
