import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    const sessionId = localStorage.getItem('session_id')

    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    } else if (sessionId) {
      config.headers['X-Session-ID'] = sessionId
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    throw error
  },
)

export const authAPI = {
  anonymous() {
    return api.post('/api/auth/anonymous')
  },

  register(username, password) {
    return api.post('/api/auth/register', { username, password })
  },

  login(username, password) {
    return api.post('/api/auth/login', { username, password })
  },

  mergeAnonymous(anonymousSessionId) {
    return api.post('/api/auth/merge-anonymous', { anonymous_session_id: anonymousSessionId })
  },
}

export const userAPI = {
  getMe() {
    return api.get('/api/user/me')
  },

  getConfig() {
    return api.get('/api/user/config')
  },

  updateConfig(data) {
    return api.put('/api/user/config', data)
  },

  testConfig(data) {
    return api.post('/api/user/config/test', data)
  },
}

export const papersAPI = {
  list(params) {
    return api.get('/api/papers', { params })
  },

  upload(formData) {
    return api.post('/api/papers/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  get(paperId) {
    return api.get(`/api/papers/${paperId}`)
  },

  update(paperId, data) {
    return api.put(`/api/papers/${paperId}`, data)
  },

  delete(paperId) {
    return api.delete(`/api/papers/${paperId}`)
  },

  reparse(paperId) {
    return api.post(`/api/papers/${paperId}/reparse`)
  },

  downloadPdf(paperId) {
    return axios.get(`${API_BASE_URL}/api/papers/${paperId}/download`, {
      responseType: 'blob',
      headers: {
        Authorization: localStorage.getItem('token')
          ? `Bearer ${localStorage.getItem('token')}`
          : '',
        'X-Session-ID': localStorage.getItem('session_id') || '',
      },
    })
  },
}

export const qaAPI = {
  ask(paperId, question, conversationId = null) {
    return api.post(`/api/qa/${paperId}`, { question, conversation_id: conversationId })
  },

  getHistory(paperId) {
    return api.get(`/api/qa/${paperId}/history`)
  },
}

export const reportsAPI = {
  generate(paperId, reportType) {
    return api.post(`/api/reports/${paperId}`, { report_type: reportType })
  },
}

export default api
