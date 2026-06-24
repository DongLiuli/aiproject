<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { usePapersStore } from '@/stores/papers'
import { X, User, Lock, Eye, EyeOff } from 'lucide-vue-next'

const props = defineProps({
  mode: {
    type: String,
    default: 'login'
  }
})

const emit = defineEmits(['close', 'success'])

const authStore = useAuthStore()
const papersStore = usePapersStore()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')

async function handleSubmit() {
  error.value = ''
  
  if (!username.value || !password.value) {
    error.value = '请填写用户名和密码'
    return
  }
  
  if (props.mode === 'register' && password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  
  loading.value = true
  
  try {
    if (props.mode === 'login') {
      await authStore.login(username.value, password.value)
    } else {
      await authStore.register(username.value, password.value)
    }
    
    await papersStore.fetchPapers()
    emit('success')
  } catch (err) {
    error.value = err.response?.data?.detail || '操作失败，请重试'
  } finally {
    loading.value = false
  }
}

function togglePassword() {
  showPassword.value = !showPassword.value
}
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h2>{{ mode === 'login' ? '登录' : '注册' }}</h2>
        <button class="close-btn" @click="$emit('close')">
          <X class="close-icon" />
        </button>
      </div>
      
      <form class="auth-form" @submit.prevent="handleSubmit">
        <div class="form-group">
          <label class="form-label">
            <User class="label-icon" />
            <span>用户名</span>
          </label>
          <input 
            type="text" 
            v-model="username"
            class="form-input"
            placeholder="请输入用户名"
            :disabled="loading"
          />
        </div>
        
        <div class="form-group">
          <label class="form-label">
            <Lock class="label-icon" />
            <span>密码</span>
          </label>
          <div class="password-input">
            <input 
              :type="showPassword ? 'text' : 'password'"
              v-model="password"
              class="form-input"
              placeholder="请输入密码"
              :disabled="loading"
            />
            <button type="button" class="password-toggle" @click="togglePassword">
              <Eye v-if="showPassword" class="toggle-icon" />
              <EyeOff v-else class="toggle-icon" />
            </button>
          </div>
        </div>
        
        <div v-if="mode === 'register'" class="form-group">
          <label class="form-label">
            <Lock class="label-icon" />
            <span>确认密码</span>
          </label>
          <input 
            type="password" 
            v-model="confirmPassword"
            class="form-input"
            placeholder="请再次输入密码"
            :disabled="loading"
          />
        </div>
        
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
        
        <button 
          type="submit" 
          class="submit-btn"
          :disabled="loading"
        >
          <span v-if="loading">处理中...</span>
          <span v-else>{{ mode === 'login' ? '登录' : '注册' }}</span>
        </button>
        
        <div class="switch-mode">
          <span>
            {{ mode === 'login' ? '还没有账号？' : '已有账号？' }}
            <button type="button" class="mode-switch-btn" @click="$emit('close', mode === 'login' ? 'register' : 'login')">
              {{ mode === 'login' ? '立即注册' : '立即登录' }}
            </button>
          </span>
        </div>
      </form>
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
  max-width: 400px;
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

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: #333;
}

.label-icon {
  width: 16px;
  height: 16px;
}

.form-input {
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 1rem;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.password-input {
  position: relative;
}

.password-toggle {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
}

.toggle-icon {
  width: 18px;
  height: 18px;
  color: #666;
}

.error-message {
  color: #ef4444;
  font-size: 0.875rem;
  padding: 8px 12px;
  background: #fef2f2;
  border-radius: 8px;
}

.submit-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  padding: 14px 24px;
  border-radius: 10px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.switch-mode {
  text-align: center;
  color: #666;
  font-size: 0.875rem;
}

.mode-switch-btn {
  background: none;
  border: none;
  color: #667eea;
  cursor: pointer;
  font-weight: 500;
  text-decoration: underline;
}
</style>