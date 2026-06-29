<script setup>
import { computed } from 'vue'
import { FileText, Clock, Trash2, RefreshCw, ChevronRight, AlertCircle } from 'lucide-vue-next'

const props = defineProps({
  paper: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['view', 'delete', 'reparse'])

const statusText = computed(() => {
  const status = props.paper.parse_status
  switch (status) {
    case 'uploaded':
      return '已上传'
    case 'parsing':
      return '解析中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    default:
      return status
  }
})

const statusClass = computed(() => {
  const status = props.paper.parse_status
  switch (status) {
    case 'uploaded':
      return 'status-uploaded'
    case 'parsing':
      return 'status-parsing'
    case 'completed':
      return 'status-completed'
    case 'failed':
      return 'status-failed'
    default:
      return ''
  }
})

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
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
  <div class="paper-card" @click="emit('view', paper)">
    <div class="card-header">
      <div class="paper-icon">
        <FileText class="icon" />
      </div>
      <div class="paper-info">
        <h3 class="paper-title">{{ paper.title || paper.file_name }}</h3>
        <div class="paper-meta">
          <span class="meta-item">
            <Clock class="meta-icon" />
            {{ formatDate(paper.upload_time) }}
          </span>
          <span class="meta-item">{{ formatSize(paper.file_size) }}</span>
        </div>
      </div>
      <span class="status-badge" :class="statusClass">
        {{ statusText }}
      </span>
    </div>

    <div
      v-if="paper.parse_status === 'failed' && paper.parse_error"
      class="parse-error"
      @click.stop
    >
      <AlertCircle class="parse-error-icon" />
      <span>{{ paper.parse_error }}</span>
    </div>

    <div v-if="paper.authors" class="paper-authors">
      {{ paper.authors }}
    </div>

    <div v-if="paper.summary" class="paper-summary">
      {{ paper.summary }}
    </div>

    <div class="card-footer">
      <div class="card-actions">
        <button class="action-btn" @click.stop="emit('reparse', paper.paper_id)" title="重新解析">
          <RefreshCw class="action-icon" />
        </button>
        <button class="action-btn delete" @click.stop="emit('delete', paper.paper_id)" title="删除">
          <Trash2 class="action-icon" />
        </button>
      </div>
      <button class="view-btn">
        <span>查看详情</span>
        <ChevronRight class="view-icon" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.paper-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: all 0.2s;
}

.paper-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}

.parse-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #fef2f2;
  color: #ef4444;
  border-radius: 8px;
  font-size: 0.8125rem;
  line-height: 1.4;
  word-break: break-word;
}

.parse-error-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 1px;
}

.paper-icon {
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon {
  width: 24px;
  height: 24px;
  color: white;
}

.paper-info {
  flex: 1;
  min-width: 0;
}

.paper-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.paper-meta {
  display: flex;
  gap: 16px;
  font-size: 0.875rem;
  color: #999;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.meta-icon {
  width: 14px;
  height: 14px;
}

.status-badge {
  padding: 4px 12px;
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

.paper-authors {
  font-size: 0.875rem;
  color: #666;
  margin-bottom: 8px;
}

.paper-summary {
  font-size: 0.875rem;
  color: #999;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 16px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  width: 32px;
  height: 32px;
  background: #f5f5f5;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #e0e0e0;
}

.action-btn.delete:hover {
  background: #fee2e2;
}

.action-btn.delete:hover .action-icon {
  color: #dc2626;
}

.action-icon {
  width: 16px;
  height: 16px;
  color: #666;
}

.view-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: #667eea;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.2s;
}

.view-btn:hover {
  color: #764ba2;
}

.view-icon {
  width: 16px;
  height: 16px;
}
</style>
