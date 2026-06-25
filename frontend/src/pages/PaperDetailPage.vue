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
  BookOpen,
  MessageSquare,
  FileOutput,
} from 'lucide-vue-next'
import PaperContent from '@/components/PaperContent.vue'
import QAInterface from '@/components/QAInterface.vue'
import ReportPanel from '@/components/ReportPanel.vue'
const route = useRoute()
const router = useRouter()
const papersStore = usePapersStore()
const activeTab = ref('content')
const paperId = computed(() => route.params.id)
const paper = computed(() => papersStore.currentPaper)
onMounted(async () => {
  if (!paperId.value) return
  try {
    await papersStore.getPaper(paperId.value)
  } catch (err) {
    console.error('Failed to load paper:', err)
  }
})
function goBack() {
  router.push('/')
}
const tabs = [
  { id: 'content', name: '论文内容', icon: BookOpen },
  { id: 'qa', name: '智能问答', icon: MessageSquare },
  { id: 'report', name: '研读报告', icon: FileOutput },
]
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

      <div class="detail-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ 'tab-active': activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <component :is="tab.icon" class="tab-icon" />
          <span>{{ tab.name }}</span>
        </button>
      </div>

      <div class="detail-content">
        <PaperContent v-if="activeTab === 'content'" :content="paper.structured_info || {}" />

        <QAInterface v-else-if="activeTab === 'qa'" :paper-id="paperId" />

        <ReportPanel v-else-if="activeTab === 'report'" :paper-id="paperId" />
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
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.detail-header {
  margin-bottom: 24px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  color: #667eea;
  font-size: 0.9375rem;
  cursor: pointer;
  transition: color 0.2s;
}

.back-btn:hover {
  color: #764ba2;
}

.back-icon {
  width: 18px;
  height: 18px;
}

.paper-header {
  display: flex;
  gap: 20px;
  padding: 24px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-bottom: 24px;
}

.paper-icon {
  width: 64px;
  height: 64px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon {
  width: 32px;
  height: 32px;
  color: white;
}

.paper-meta {
  flex: 1;
}

.paper-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 16px 0;
}

.meta-info {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9375rem;
  color: #666;
}

.meta-icon {
  width: 18px;
  height: 18px;
}

.status-badge {
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 0.875rem;
  font-weight: 500;
  flex-shrink: 0;
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

.detail-tabs {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 24px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  cursor: pointer;
  font-size: 0.9375rem;
  font-weight: 500;
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
  width: 18px;
  height: 18px;
}

.detail-content {
  min-height: 500px;
}

@media (max-width: 768px) {
  .paper-header {
    flex-direction: column;
  }

  .paper-title {
    font-size: 1.25rem;
  }

  .meta-info {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
