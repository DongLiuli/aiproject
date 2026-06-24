<script setup>import { ref, watch } from 'vue';
import { useUserStore } from '@/stores/user';
import { X, Save, CheckCircle, AlertCircle } from 'lucide-vue-next';
const emit = defineEmits(['close']);
const userStore = useUserStore();
const config = ref({ ...userStore.config });
const testResult = ref(null);
const saving = ref(false);
watch(() => userStore.config, (newConfig) => {
 config.value = { ...newConfig };
}, { deep: true });
async function saveConfig() {
 saving.value = true;
 try {
 await userStore.updateConfig(config.value);
 testResult.value = { success: true, message: '配置保存成功' };
 }
 catch (err) {
 testResult.value = { success: false, message: '保存失败，请重试' };
 }
 finally {
 saving.value = false;
 }
}
async function testConfig() {
 try {
 const success = await userStore.testConfig();
 testResult.value = success
 ? { success: true, message: '配置测试成功' }
 : { success: false, message: '配置测试失败，请检查API密钥' };
 }
 catch (err) {
 testResult.value = { success: false, message: '测试失败，请检查网络连接' };
 }
}
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h2>系统设置</h2>
        <button class="close-btn" @click="$emit('close')">
          <X class="close-icon" />
        </button>
      </div>
      
      <div class="settings-form">
        <div class="form-section">
          <h3>LLM 配置</h3>
          
          <div class="form-group">
            <label class="form-label">模型选择</label>
            <select v-model="config.llm_model" class="form-select">
              <option value="deepseek-chat">DeepSeek Chat</option>
              <option value="qwen-turbo">Qwen Turbo</option>
              <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
            </select>
          </div>
          
          <div class="form-group">
            <label class="form-label">API 基础 URL</label>
            <input 
              type="text" 
              v-model="config.llm_base_url"
              class="form-input"
              placeholder="https://api.deepseek.com"
            />
          </div>
          
          <div class="form-group">
            <label class="form-label">API Key</label>
            <input 
              type="password" 
              v-model="config.llm_api_key"
              class="form-input"
              placeholder="请输入您的 API Key"
            />
            <p class="form-hint">
              您的 API Key 不会被存储在服务端，仅用于本次会话
            </p>
          </div>
        </div>
        
        <div v-if="testResult" 
          class="test-result"
          :class="{ 'test-success': testResult.success, 'test-error': !testResult.success }"
        >
          <CheckCircle v-if="testResult.success" class="result-icon" />
          <AlertCircle v-else class="result-icon" />
          <span>{{ testResult.message }}</span>
        </div>
      </div>
      
      <div class="modal-actions">
        <button class="test-btn" @click="testConfig">
          测试配置
        </button>
        <button class="cancel-btn" @click="$emit('close')">
          取消
        </button>
        <button 
          class="save-btn"
          :disabled="saving"
          @click="saveConfig"
        >
          <Save class="save-icon" />
          <span v-if="saving">保存中...</span>
          <span v-else>保存</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  padding: 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.modal-header h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: #1a1a1a;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  transition: background 0.2s;
}

.close-btn:hover {
  background: #f0f0f0;
}

.close-icon {
  width: 20px;
  height: 20px;
  color: #666;
}

.settings-form {
  margin-bottom: 24px;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-section h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-weight: 500;
  color: #333;
}

.form-input {
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 1rem;
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: #667eea;
}

.form-select {
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 1rem;
  background: white;
  cursor: pointer;
  transition: border-color 0.2s;
}

.form-select:focus {
  outline: none;
  border-color: #667eea;
}

.form-hint {
  font-size: 0.875rem;
  color: #999;
}

.test-result {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  margin-top: 16px;
}

.test-success {
  background: #f0fdf4;
  color: #16a34a;
}

.test-error {
  background: #fef2f2;
  color: #ef4444;
}

.result-icon {
  width: 20px;
  height: 20px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.test-btn {
  padding: 12px 20px;
  border: 1px solid #667eea;
  border-radius: 10px;
  background: white;
  color: #667eea;
  cursor: pointer;
  font-weight: 500;
  transition: background 0.2s;
}

.test-btn:hover {
  background: #f5f7ff;
}

.cancel-btn {
  padding: 12px 24px;
  border: 1px solid #ddd;
  border-radius: 10px;
  background: white;
  color: #666;
  cursor: pointer;
  transition: background 0.2s;
}

.cancel-btn:hover {
  background: #f5f5f5;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 500;
  transition: transform 0.2s;
}

.save-btn:hover:not(:disabled) {
  transform: translateY(-2px);
}

.save-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.save-icon {
  width: 18px;
  height: 18px;
}
</style>