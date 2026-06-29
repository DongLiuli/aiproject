<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { usePapersStore } from '@/stores/papers'
import { useUIStore } from '@/stores/ui'
import { BookOpen, Upload, Settings, User, LogOut, LogIn, Menu, X } from 'lucide-vue-next'

const authStore = useAuthStore()
const papersStore = usePapersStore()
const uiStore = useUIStore()

const showMenu = ref(false)
const showAuthModal = ref(false)
const authMode = ref('login')

onMounted(async () => {
  await authStore.initialize()
  await papersStore.fetchPapers()
})

async function handleLogout() {
  await authStore.logout()
  await papersStore.fetchPapers()
}

function openAuth(mode) {
  authMode.value = mode
  showAuthModal.value = true
}

function handleAuthClose(newMode) {
  if (newMode) {
    authMode.value = newMode
  } else {
    showAuthModal.value = false
  }
}
</script>

<template>
  <div class="layout">
    <header class="header">
      <div class="header-content">
        <div class="logo">
          <BookOpen class="logo-icon" />
          <span class="logo-text">科研文献解析</span>
        </div>

        <nav class="nav" :class="{ 'nav-visible': showMenu }">
          <router-link to="/" class="nav-link">
            <BookOpen class="nav-icon" />
            <span>文献库</span>
          </router-link>
        </nav>

        <div class="header-actions">
          <button class="action-btn" @click="uiStore.openUploadModal()">
            <Upload class="action-icon" />
            <span>上传论文</span>
          </button>

          <button class="action-btn" @click="uiStore.openSettingsModal()">
            <Settings class="action-icon" />
          </button>

          <div v-if="authStore.user" class="user-menu">
            <button class="user-btn">
              <User class="user-icon" />
              <span>{{ authStore.user.username }}</span>
            </button>
            <button class="logout-btn" @click="handleLogout">
              <LogOut class="logout-icon" />
              <span>退出</span>
            </button>
          </div>

          <div v-else class="auth-actions">
            <button class="auth-btn" @click="openAuth('login')">
              <LogIn class="auth-icon" />
              <span>登录</span>
            </button>
            <button class="auth-btn register" @click="openAuth('register')">
              <User class="auth-icon" />
              <span>注册</span>
            </button>
          </div>

          <button class="mobile-menu-btn" @click="showMenu = !showMenu">
            <Menu v-if="!showMenu" class="menu-icon" />
            <X v-else class="menu-icon" />
          </button>
        </div>
      </div>
    </header>

    <main class="main-content">
      <slot></slot>
    </main>

    <AuthModal
      v-if="showAuthModal"
      :mode="authMode"
      @close="handleAuthClose"
      @success="showAuthModal = false"
    />
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

.header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 0 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  width: 32px;
  height: 32px;
}

.logo-text {
  font-size: 1.25rem;
  font-weight: 600;
}

.nav {
  display: flex;
  gap: 20px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: white;
  text-decoration: none;
  padding: 8px 16px;
  border-radius: 8px;
  transition: background 0.2s;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.1);
}

.nav-icon {
  width: 20px;
  height: 20px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.3);
}

.action-icon {
  width: 18px;
  height: 18px;
}

.user-menu {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.15);
  padding: 4px;
  border-radius: 8px;
}

.user-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  color: white;
  cursor: pointer;
  padding: 4px 12px;
}

.user-icon {
  width: 20px;
  height: 20px;
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  padding: 4px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.logout-btn:hover {
  background: rgba(239, 68, 68, 0.3);
}

.logout-icon {
  width: 16px;
  height: 16px;
}

.auth-actions {
  display: flex;
  gap: 8px;
}

.auth-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.15);
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.auth-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}

.auth-btn.register {
  background: rgba(255, 255, 255, 0.95);
  color: #667eea;
}

.auth-btn.register:hover {
  background: white;
}

.auth-icon {
  width: 18px;
  height: 18px;
}

.mobile-menu-btn {
  display: none;
  background: none;
  border: none;
  color: white;
  cursor: pointer;
}

.menu-icon {
  width: 24px;
  height: 24px;
}

@media (max-width: 768px) {
  .nav {
    position: absolute;
    top: 64px;
    left: 0;
    right: 0;
    background: #667eea;
    flex-direction: column;
    padding: 16px;
    gap: 8px;
    display: none;
  }

  .nav-visible {
    display: flex;
  }

  .mobile-menu-btn {
    display: block;
  }

  .header-actions button span {
    display: none;
  }
}
</style>
