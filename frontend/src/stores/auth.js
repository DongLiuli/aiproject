import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authAPI } from '@/api'
export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('token'))
  const sessionId = ref(localStorage.getItem('session_id'))
  const isAnonymous = ref(!token.value)
  async function initialize() {
    if (!token.value && !sessionId.value) {
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
      user.value = { id: response.user_id, username: response.username }
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
      user.value = { id: response.user_id, username: response.username }
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
    user.value = null
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
