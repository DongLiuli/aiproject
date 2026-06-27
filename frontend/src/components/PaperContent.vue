<template>
  <div class="paper-content">
    <div v-if="loading" class="loading">
      <div class="spinner"></div>
      <p>正在加载论文...</p>
    </div>
    <div v-else-if="pdfUrl" class="pdf-viewer">
      <iframe :src="pdfUrl" title="论文PDF" class="pdf-frame"></iframe>
    </div>
    <div v-else-if="error === 'pdf_not_found'" class="empty">
      <p>PDF 文件暂不可用</p>
      <p class="hint">可能是页面刷新后缓存丢失，请重新上传论文</p>
    </div>
    <div v-else class="empty">
      <p>{{ error || '请先上传论文' }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { getPDFUrl } from '@/utils/pdfStorage'

const props = defineProps({
  paper: {
    type: Object,
    default: () => ({}),
  },
})

const pdfUrl = ref('')
const loading = ref(true)
const error = ref(null)

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
    const url = await getPDFUrl(props.paper.paper_id)

    if (url) {
      pdfUrl.value = url
    } else {
      error.value = 'pdf_not_found'
    }
  } catch (err) {
    console.error('加载 PDF 失败:', err)
    error.value = '加载失败'
  } finally {
    loading.value = false
  }
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
</script>

<style scoped>
.paper-content {
  width: 100%;
  min-height: 800px;
  background: #f8f9fa;
  border-radius: 8px;
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
  width: 100%;
  height: 800px;
  overflow: auto;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: none;
  background: white;
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
</style>
