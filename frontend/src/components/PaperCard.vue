<script setup>
import { computed } from 'vue'
import { FileText, Clock, Trash2, RefreshCw, ChevronRight, Check } from 'lucide-vue-next'

const props = defineProps({
  paper: {
    type: Object,
    required: true,
  },
  // 对比多选模式
  selectable: {
    type: Boolean,
    default: false,
  },
  selected: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['view', 'delete', 'reparse', 'toggle-select'])

// 仅已完成解析的论文可参与对比
const selectDisabled = computed(() => props.paper.parse_status !== 'completed')

function handleCardClick() {
  if (props.selectable) {
    if (!selectDisabled.value) emit('toggle-select', props.paper)
    return
  }
  emit('view', props.paper)
}

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
  <div
    class="paper-card"
    :class="{ selectable, selected, 'select-disabled': selectable && selectDisabled }"
    @click="handleCardClick"
  >
    <div v-if="selectable" class="select-check" :class="{ checked: selected }">
      <Check v-if="selected" class="check-icon" />
    </div>

    <div
      v-if="selectable && selectDisabled"
      class="select-overlay"
      title="仅已完成解析的论文可对比"
    >
      未完成解析，不可对比
    </div>

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

    <div v-if="paper.authors" class="paper-authors">
      {{ paper.authors }}
    </div>

    <div v-if="paper.summary" class="paper-summary">
      {{ paper.summary }}
    </div>

    <div v-if="paper.parse_status === 'failed' && paper.parse_error" class="parse-error">
      <div class="parse-error-msg">{{ paper.parse_error }}</div>
      <div class="parse-error-hint">
        可点击下方「↻」重新解析；若提示未配置 API Key，请先到「设置」填写后再试。
      </div>
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
  position: relative;
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.paper-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.paper-card.selectable {
  padding-left: 52px;
}

.paper-card.selected {
  border-color: #667eea;
  box-shadow: 0 4px 16px rgba(102, 126, 234, 0.25);
}

.paper-card.select-disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.select-check {
  position: absolute;
  top: 20px;
  left: 16px;
  width: 22px;
  height: 22px;
  border: 2px solid #cbd5e1;
  border-radius: 6px;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.select-check.checked {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
}

.check-icon {
  width: 14px;
  height: 14px;
  color: white;
}

.select-overlay {
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 0.75rem;
  color: #dc2626;
  background: #fef2f2;
  padding: 2px 8px;
  border-radius: 6px;
}

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
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

.parse-error {
  font-size: 0.875rem;
  background: #fef2f2;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 16px;
  border-left: 3px solid #dc2626;
}

.parse-error-msg {
  color: #dc2626;
}

.parse-error-hint {
  margin-top: 6px;
  font-size: 0.8125rem;
  color: #b45309;
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
