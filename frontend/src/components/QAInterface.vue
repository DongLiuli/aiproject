<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useQAStore } from '@/stores/papers'
import { Send, Loader2, MessageSquare, FileText, Link } from 'lucide-vue-next'
import { renderContent } from '@/utils/markdown'

const props = defineProps({
  paperId: {
    type: String,
    required: true
  },
  parseStatus: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['scroll-to-section'])

const canAsk = computed(() => props.parseStatus === 'completed')
const qaStore = useQAStore()
const question = ref('')
const messages = ref([])
const messagesEl = ref(null)

function scrollToSection(source) {
  emit('scroll-to-section', source.page, source.section)
}

watch(() => props.paperId, async (newId) => {
  if (newId) {
    await loadHistory()
  }
}, { immediate: true })

function scrollToBottom() {
  nextTick(() => {
    const el = messagesEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function loadHistory() {
  try {
    const conversations = await qaStore.getConversationHistory(props.paperId)
    const ordered = [...(conversations || [])].reverse()
    const flat = []
    for (const conv of ordered) {
      let pending = null
      for (const m of conv.messages || []) {
        if (m.role === 'user') {
          if (pending) flat.push(pending)
          pending = { question: m.content, answer: null, sources: [], timestamp: m.created_at }
        } else if (m.role === 'assistant') {
          if (pending) {
            pending.answer = m.content
            pending.sources = m.sources || []
            pending.timestamp = m.created_at
            flat.push(pending)
            pending = null
          } else {
            flat.push({ question: '', answer: m.content, sources: m.sources || [], timestamp: m.created_at })
          }
        }
      }
      if (pending) flat.push(pending)
    }
    messages.value = flat
    scrollToBottom()
  }
  catch (err) {
    console.error('Failed to load history:', err)
  }
}

async function sendQuestion() {
  if (!question.value.trim() || qaStore.answering || !canAsk.value)
    return
  const newQuestion = question.value.trim()
  messages.value.push({
    question: newQuestion,
    answer: '',
    sources: [],
    loading: true
  })
  const index = messages.value.length - 1
  question.value = ''
  scrollToBottom()
  try {
    await qaStore.askQuestionStream(props.paperId, newQuestion, {
      onSources: (sources) => {
        messages.value[index].sources = sources
      },
      onDelta: (fullAnswer) => {
        messages.value[index].loading = false
        messages.value[index].answer = fullAnswer
        scrollToBottom()
      },
    })
    messages.value[index].loading = false
    messages.value[index].timestamp = new Date().toISOString()
    scrollToBottom()
  }
  catch (err) {
    messages.value[index] = {
      question: newQuestion,
      answer: err.userMessage || '抱歉，回答失败，请重试',
      sources: [],
      error: true
    }
  }
}

function formatDate(dateStr) {
  if (!dateStr)
    return ''
  const date = new Date(dateStr)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="qa-container">
    <div class="qa-header">
      <MessageSquare class="qa-icon" />
      <h3>智能问答</h3>
    </div>
    
    <div class="qa-messages" ref="messagesEl">
      <div v-if="messages.length === 0" class="empty-state">
        <MessageSquare class="empty-icon" />
        <p>向论文提出问题，获取智能回答</p>
      </div>
      
      <div 
        v-for="(msg, index) in messages" 
        :key="index"
        class="message-item"
      >
        <div class="message-question">
          <div class="question-header">
            <span class="question-label">问题</span>
            <span v-if="msg.timestamp" class="message-time">{{ formatDate(msg.timestamp) }}</span>
          </div>
          <p>{{ msg.question }}</p>
        </div>
        
        <div class="message-answer" :class="{ 'answer-loading': msg.loading, 'answer-error': msg.error }">
          <div v-if="msg.loading" class="loading-spinner">
            <Loader2 class="spinner" />
            <span>正在思考...</span>
          </div>
          <div v-else>
            <div class="answer-header">
              <span class="answer-label">回答</span>
            </div>
            <div class="answer-content" v-html="renderContent(msg.answer)"></div>
            
            <div v-if="msg.sources && msg.sources.length > 0" class="answer-sources">
              <div class="sources-header">
                <FileText class="sources-icon" />
                <span>来源</span>
              </div>
              <ul class="sources-list">
                <li v-for="(source, idx) in msg.sources" :key="idx" class="source-item">
                  <button 
                    class="source-link" 
                    @click="scrollToSection(source)"
                    :title="source.section ? `跳转到${source.section}` : `跳转到第${source.page}页`"
                  >
                    <Link class="link-icon" />
                    <span class="source-page">{{ source.page ? `第 ${source.page} 页` : '' }}</span>
                    <span v-if="source.section" class="source-section">{{ source.section }}</span>
                  </button>
                  <span v-if="source.text" class="source-snippet">{{ source.text.substring(0, 80) }}...</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div v-if="!canAsk" class="qa-locked-hint">
      论文解析完成后即可提问
    </div>
    <div class="qa-input-area">
      <input
        type="text"
        v-model="question"
        class="qa-input"
        :placeholder="canAsk ? '输入您的问题...' : '论文解析完成后即可提问'"
        @keyup.enter="sendQuestion"
        :disabled="qaStore.answering || !canAsk"
      />
      <button
        class="send-btn"
        :disabled="!question.trim() || qaStore.answering || !canAsk"
        @click="sendQuestion"
      >
        <Send class="send-icon" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.qa-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.qa-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
}

.qa-icon {
  width: 20px;
  height: 20px;
  color: #667eea;
}

.qa-header h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #333;
}

.qa-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #999;
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.message-item {
  margin-bottom: 24px;
}

.message-item:last-child {
  margin-bottom: 0;
}

.message-question {
  margin-bottom: 12px;
}

.question-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.question-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #667eea;
}

.message-time {
  font-size: 0.75rem;
  color: #999;
}

.message-question p {
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 10px;
  font-size: 0.9375rem;
  line-height: 1.6;
}

.message-answer {
  border-left: 3px solid #667eea;
  padding-left: 16px;
}

.answer-loading {
  min-height: 80px;
}

.loading-spinner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
}

.spinner {
  width: 24px;
  height: 24px;
  color: #667eea;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.answer-header {
  margin-bottom: 8px;
}

.answer-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #10b981;
}

.answer-content {
  font-size: 0.9375rem;
  line-height: 1.8;
  color: #333;
}

.answer-content :deep(pre) {
  background: #f5f7fa;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.875rem;
}

.answer-content :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.875rem;
}

.answer-content :deep(pre code) {
  background: none;
  padding: 0;
}

.answer-content :deep(blockquote) {
  border-left: 3px solid #667eea;
  padding-left: 12px;
  margin: 12px 0;
  color: #666;
}

.answer-content :deep(h1),
.answer-content :deep(h2),
.answer-content :deep(h3) {
  margin: 16px 0 8px;
  font-weight: 600;
}

.answer-content :deep(h1) { font-size: 1.25rem; }
.answer-content :deep(h2) { font-size: 1.125rem; }
.answer-content :deep(h3) { font-size: 1rem; }

.answer-content :deep(ul),
.answer-content :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.answer-content :deep(li) {
  margin: 4px 0;
}

.answer-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}

.answer-content :deep(th),
.answer-content :deep(td) {
  border: 1px solid #e0e0e0;
  padding: 8px 12px;
  text-align: left;
  font-size: 0.875rem;
}

.answer-content :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

.answer-content :deep(.katex) {
  font-size: 1.1em;
}

.answer-content :deep(.katex-display) {
  margin: 12px 0;
  overflow-x: auto;
}

.answer-error .answer-content {
  color: #ef4444;
}

.answer-sources {
  margin-top: 16px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 8px;
}

.sources-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  color: #666;
  margin-bottom: 8px;
}

.sources-icon {
  width: 14px;
  height: 14px;
}

.sources-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.source-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
  border-bottom: 1px dashed #e0e0e0;
}

.source-item:last-child {
  border-bottom: none;
}

.source-link {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  color: #667eea;
  font-size: 0.875rem;
  transition: color 0.2s;
}

.source-link:hover {
  color: #764ba2;
}

.link-icon {
  width: 14px;
  height: 14px;
}

.source-page {
  font-weight: 500;
}

.source-section {
  color: #999;
  font-size: 0.8125rem;
}

.source-snippet {
  font-size: 0.8125rem;
  color: #999;
  line-height: 1.5;
  padding-left: 20px;
}

.qa-locked-hint {
  padding: 10px 20px;
  font-size: 0.8125rem;
  color: #d97706;
  background: #fef3c7;
  text-align: center;
}

.qa-input-area {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.qa-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 0.9375rem;
  transition: border-color 0.2s;
}

.qa-input:focus {
  outline: none;
  border-color: #667eea;
}

.qa-input:disabled {
  background: #f0f0f0;
}

.send-btn {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-2px);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-icon {
  width: 18px;
  height: 18px;
  color: white;
}
</style>