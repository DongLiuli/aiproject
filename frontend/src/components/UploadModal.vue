<script setup>import { ref } from 'vue';
import { usePapersStore } from '@/stores/papers';
import { useUserStore } from '@/stores/user';
import { X, Upload, FileText, AlertCircle } from 'lucide-vue-next';
const emit = defineEmits(['close']);
const papersStore = usePapersStore();
const userStore = useUserStore();
const file = ref(null);
const error = ref('');
const acceptedTypes = ['application/pdf'];
const maxSize = 50 * 1024 * 1024;
function handleFileSelect(event) {
 const selectedFile = event.target.files[0];
 if (!selectedFile)
 return;
 if (!acceptedTypes.includes(selectedFile.type)) {
 error.value = '请选择 PDF 格式的文件';
 return;
 }
 if (selectedFile.size > maxSize) {
 error.value = '文件大小不能超过 50MB';
 return;
 }
 error.value = '';
 file.value = selectedFile;
}
function handleDragOver(event) {
 event.preventDefault();
}
function handleDrop(event) {
 event.preventDefault();
 const droppedFile = event.dataTransfer.files[0];
 if (!droppedFile)
 return;
 if (!acceptedTypes.includes(droppedFile.type)) {
 error.value = '请选择 PDF 格式的文件';
 return;
 }
 if (droppedFile.size > maxSize) {
 error.value = '文件大小不能超过 50MB';
 return;
 }
 error.value = '';
 file.value = droppedFile;
}
async function handleUpload() {
 if (!file.value) {
 error.value = '请先选择文件';
 return;
 }
 if (!userStore.config.llm_api_key) {
 error.value = '请先在设置页配置 API Key';
 return;
 }
 try {
 await papersStore.uploadPaper(file.value);
 emit('close');
 }
 catch (err) {
 error.value = err.response?.data?.detail || '上传失败，请重试';
 }
}
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h2>上传论文</h2>
        <button class="close-btn" @click="$emit('close')">
          <X class="close-icon" />
        </button>
      </div>
      
      <div 
        class="drop-zone"
        :class="{ 'drop-zone-active': file }"
        @dragover="handleDragOver"
        @drop="handleDrop"
        @click="$refs.fileInput.click()"
      >
        <input 
          ref="fileInput"
          type="file" 
          accept=".pdf"
          class="file-input"
          @change="handleFileSelect"
        />
        
        <div v-if="!file" class="drop-content">
          <div class="drop-icon">
            <Upload class="upload-icon" />
          </div>
          <p class="drop-title">拖拽 PDF 文件到此处</p>
          <p class="drop-hint">或点击选择文件</p>
          <p class="drop-info">支持 PDF 格式，最大 50MB</p>
        </div>
        
        <div v-else class="file-preview">
          <FileText class="file-icon" />
          <div class="file-info">
            <p class="file-name">{{ file.name }}</p>
            <p class="file-size">{{ (file.size / 1024 / 1024).toFixed(2) }} MB</p>
          </div>
          <button class="clear-btn" @click.stop="file = null">
            <X class="clear-icon" />
          </button>
        </div>
      </div>
      
      <div v-if="error" class="error-message">
        <AlertCircle class="error-icon" />
        <span>{{ error }}</span>
      </div>
      
      <div class="modal-actions">
        <button class="cancel-btn" @click="$emit('close')">
          取消
        </button>
        <button 
          class="upload-btn"
          :disabled="!file || papersStore.uploading"
          @click="handleUpload"
        >
          <span v-if="papersStore.uploading">上传中...</span>
          <span v-else>上传</span>
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
  max-width: 480px;
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

.drop-zone {
  border: 2px dashed #ddd;
  border-radius: 12px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
}

.drop-zone:hover {
  border-color: #667eea;
  background: #f5f7ff;
}

.drop-zone-active {
  border-color: #667eea;
  background: #f5f7ff;
}

.file-input {
  display: none;
}

.drop-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.drop-icon {
  width: 64px;
  height: 64px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-icon {
  width: 32px;
  height: 32px;
  color: white;
}

.drop-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: #333;
}

.drop-hint {
  color: #666;
}

.drop-info {
  font-size: 0.875rem;
  color: #999;
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: white;
  border-radius: 10px;
  border: 1px solid #e0e0e0;
}

.file-icon {
  width: 48px;
  height: 48px;
  color: #667eea;
}

.file-info {
  flex: 1;
}

.file-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
}

.file-size {
  font-size: 0.875rem;
  color: #999;
}

.clear-btn {
  background: #f0f0f0;
  border: none;
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.clear-btn:hover {
  background: #e0e0e0;
}

.clear-icon {
  width: 18px;
  height: 18px;
  color: #666;
}

.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ef4444;
  padding: 12px;
  background: #fef2f2;
  border-radius: 8px;
  margin-top: 16px;
  font-size: 0.875rem;
}

.error-icon {
  width: 18px;
  height: 18px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
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

.upload-btn {
  padding: 12px 32px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 500;
  transition: transform 0.2s, box-shadow 0.2s;
}

.upload-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.upload-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
</style>