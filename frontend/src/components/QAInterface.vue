<script setup>import { ref, watch, nextTick, computed } from 'vue';
import { useQAStore } from '@/stores/papers';
import { Send, Loader2, MessageSquare, FileText } from 'lucide-vue-next';
const props = defineProps({
 paperId: {
 type: String,
 required: true
 },
 parseStatus: {
 type: String,
 default: ''
 }
});
const canAsk = computed(() => props.parseStatus === 'completed');
const qaStore = useQAStore();
const question = ref('');
const messages = ref([]);
const messagesEl = ref(null);
watch(() => props.paperId, async (newId) => {
 if (newId) {
 await loadHistory();
 }
}, { immediate: true });
function scrollToBottom() {
 nextTick(() => {
 const el = messagesEl.value;
 if (el) el.scrollTop = el.scrollHeight;
 });
}
async function loadHistory() {
 try {
 const conversations = await qaStore.getConversationHistory(props.paperId);
 // 接口按 created_at 倒序返回对话，反转为正序（最早的在最上面）
 const ordered = [...(conversations || [])].reverse();
 const flat = [];
 for (const conv of ordered) {
 let pending = null;
 for (const m of conv.messages || []) {
 if (m.role === 'user') {
 if (pending) flat.push(pending);
 pending = { question: m.content, answer: null, sources: [], timestamp: m.created_at };
 } else if (m.role === 'assistant') {
 if (pending) {
 pending.answer = m.content;
 pending.sources = m.sources || [];
 pending.timestamp = m.created_at;
 flat.push(pending);
 pending = null;
 } else {
 flat.push({ question: '', answer: m.content, sources: m.sources || [], timestamp: m.created_at });
 }
 }
 }
 if (pending) flat.push(pending);
 }
 messages.value = flat;
 scrollToBottom();
 }
 catch (err) {
 console.error('Failed to load history:', err);
 }
}
async function sendQuestion() {
 if (!question.value.trim() || qaStore.answering || !canAsk.value)
 return;
 const newQuestion = question.value.trim();
 messages.value.push({
 question: newQuestion,
 answer: '',
 sources: [],
 loading: true
 });
 const index = messages.value.length - 1;
 question.value = '';
 scrollToBottom();
 try {
 await qaStore.askQuestionStream(props.paperId, newQuestion, {
 onSources: (sources) => {
 messages.value[index].sources = sources;
 },
 onDelta: (fullAnswer) => {
 // 首个增量到达即结束「正在思考」，逐字渲染
 messages.value[index].loading = false;
 messages.value[index].answer = fullAnswer;
 scrollToBottom();
 },
 });
 messages.value[index].loading = false;
 messages.value[index].timestamp = new Date().toISOString();
 scrollToBottom();
 }
 catch (err) {
 messages.value[index] = {
 question: newQuestion,
 answer: err.userMessage || '抱歉，回答失败，请重试',
 sources: [],
 error: true
 };
 }
}
function formatDate(dateStr) {
 if (!dateStr)
 return '';
 const date = new Date(dateStr);
 return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
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
            <p>{{ msg.answer }}</p>
            
            <div v-if="msg.sources && msg.sources.length > 0" class="answer-sources">
              <div class="sources-header">
                <FileText class="sources-icon" />
                <span>来源</span>
              </div>
              <ul class="sources-list">
                <li v-for="(source, idx) in msg.sources" :key="idx">
                  {{ source.page ? `第 ${source.page} 页` : '' }}
                  <span v-if="source.text">{{ source.text.substring(0, 50) }}...</span>
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

.message-answer p {
  font-size: 0.9375rem;
  line-height: 1.8;
  color: #333;
  white-space: pre-wrap;
}

.answer-error p {
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
  padding-left: 16px;
}

.sources-list li {
  font-size: 0.8125rem;
  color: #999;
  line-height: 1.6;
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