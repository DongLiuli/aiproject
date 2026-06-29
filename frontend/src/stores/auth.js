import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authAPI, userAPI } from '@/api'
export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token'))
  // 仅在有 token 时才恢复用户信息，避免退出后残留的 user 让界面误判为已登录
  const user = ref(token.value ? loadStoredUser() : null)
  const sessionId = ref(localStorage.getItem('session_id'))
  const isAnonymous = ref(!token.value)

  function loadStoredUser() {
    try {
      const raw = localStorage.getItem('user')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  function persistUser(value) {
    user.value = value
    if (value) {
      localStorage.setItem('user', JSON.stringify(value))
    } else {
      localStorage.removeItem('user')
    }
  }

  async function initialize() {
    // 有 token：恢复并校验登录态（修复刷新后界面误显示为未登录）
    if (token.value) {
      isAnonymous.value = false
      try {
        const me = await userAPI.getMe()
        persistUser({ id: me.user_id, username: me.username })
      } catch (error) {
        // token 失效（过期/换库等）：清理后回退到匿名身份
        token.value = null
        isAnonymous.value = true
        persistUser(null)
        localStorage.removeItem('token')
        await createAnonymousSession()
      }
      return
    }
    if (!sessionId.value) {
      await createAnonymousSession()
    }
  }
  async function createAnonymousSession() {
    try {
      const response = await authAPI.anonymous()
      sessionId.value = response.session_id
      isAnonymous.value = true
      localStorage.setItem('session_id', sessionId.value)
    } catch (error) {
      console.error('Failed to create anonymous session:', error)
    }
  }
  async function login(username, password) {
    try {
      const oldSessionId = sessionId.value
      const response = await authAPI.login(username, password)
      token.value = response.token
      persistUser({ id: response.user_id, username: response.username })
      isAnonymous.value = false
      localStorage.setItem('token', token.value)
      localStorage.removeItem('session_id')
      sessionId.value = null

      return {
        user: user.value,
        token: token.value,
        hasAnonymousData: response.has_anonymous_data || false,
        anonymousDataSummary: response.anonymous_data_summary || null,
        oldSessionId: oldSessionId,
      }
    } catch (error) {
      throw error
    }
  }
  async function register(username, password) {
    try {
      const response = await authAPI.register(username, password)
      token.value = response.token
      persistUser({ id: response.user_id, username: response.username })
      isAnonymous.value = false
      localStorage.setItem('token', token.value)
      localStorage.removeItem('session_id')
      sessionId.value = null
    } catch (error) {
      throw error
    }
  }
  async function logout() {
    token.value = null
    persistUser(null)
    isAnonymous.value = true
    localStorage.removeItem('token')
    await createAnonymousSession()
  }
  async function mergeAccount(username, password) {
    try {
      const response = await authAPI.mergeAnonymous(sessionId.value)
      await login(username, password)
      return response
    } catch (error) {
      throw error
    }
  }

  async function confirmMerge(oldSessionId) {
    return await authAPI.mergeAnonymous(oldSessionId)
  }

  return {
    user,
    token,
    sessionId,
    isAnonymous,
    initialize,
    login,
    register,
    logout,
    mergeAccount,
    confirmMerge,
  }
})
