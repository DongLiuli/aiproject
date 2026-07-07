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
    const detail = error.response?.data?.detail
    error.userMessage =
      detail?.error?.message ||
      (typeof detail === 'string' ? detail : '') ||
      error.message ||
      '操作失败，请重试'
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

  // 首页精选推荐（功能 C）：管理员推荐位 + 标签匹配
  recommendations(limit = 6) {
    return api.get('/api/papers/recommendations', { params: { limit } })
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

  // 收藏推荐论文到「我的知识库」：后端各存一份完整副本，返回新 paper_id
  collect(paperId) {
    return api.post(`/api/papers/${paperId}/collect`)
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

// 知识图谱（功能 D）：论文引用 + 共用数据集/方法关系图
export const graphAPI = {
  // paperIds 可选：传数组则只对选中论文构图；不传/空则用全部 completed 论文
  get(paperIds) {
    const params = {}
    if (paperIds && paperIds.length) params.paper_ids = paperIds.join(',')
    // 首次可能触发多篇论文的 LLM 实体抽取，给更长超时（之后走文件缓存会很快）
    return api.get('/api/graph', { params, timeout: 120000 })
  },
}

/**
 * 通用 SSE 流式请求：用原生 fetch 读取 ReadableStream，逐个解析 `data: {json}` 事件。
 * axios 不适合读流，故单独实现，并手动带上鉴权头（参照 downloadPdf）。
 * @param {string} path 接口路径（相对 API_BASE_URL）
 * @param {object} body 请求体
 * @param {(evt:object)=>void} onEvent 每个 SSE 事件回调
 */
async function streamSSE(path, body, onEvent) {
  const headers = { 'Content-Type': 'application/json' }
  const token = localStorage.getItem('token')
  const sessionId = localStorage.getItem('session_id')
  if (token) headers.Authorization = `Bearer ${token}`
  else if (sessionId) headers['X-Session-ID'] = sessionId

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })

  // 开流前的错误（校验失败等）仍是标准 JSON 结构，解析出可读消息
  if (!res.ok || !res.body) {
    let msg = '请求失败，请重试'
    try {
      const data = await res.json()
      msg = data?.detail?.error?.message || (typeof data?.detail === 'string' ? data.detail : '') || msg
    } catch {
      /* 忽略解析失败，用默认文案 */
    }
    const err = new Error(msg)
    err.userMessage = msg
    throw err
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, sep).trim()
      buffer = buffer.slice(sep + 2)
      if (!chunk.startsWith('data:')) continue
      const payload = chunk.slice(5).trim()
      if (!payload) continue
      try {
        onEvent(JSON.parse(payload))
      } catch {
        /* 忽略单条解析失败 */
      }
    }
  }
}

export const qaAPI = {
  ask(paperId, question, conversationId = null) {
    return api.post(`/api/qa/${paperId}`, { question, conversation_id: conversationId })
  },

  /**
   * 流式提问。onSources 收到来源，onDelta 收到累积答案文本。
   * 返回 { answer, sources, conversation_id }；出错抛带 userMessage 的 Error。
   */
  async askStream(paperId, question, { conversationId = null, onSources, onDelta } = {}) {
    let answer = ''
    let sources = []
    let conversationIdOut = null
    let streamError = null
    await streamSSE(`/api/qa/${paperId}/stream`, { question, conversation_id: conversationId }, (evt) => {
      if (evt.type === 'sources') {
        sources = evt.sources || []
        onSources?.(sources)
      } else if (evt.type === 'delta') {
        answer += evt.content || ''
        onDelta?.(answer)
      } else if (evt.type === 'done') {
        conversationIdOut = evt.conversation_id || null
      } else if (evt.type === 'error') {
        streamError = evt.message || '回答失败，请重试'
      }
    })
    if (streamError) {
      const err = new Error(streamError)
      err.userMessage = streamError
      throw err
    }
    return { answer, sources, conversation_id: conversationIdOut }
  },

  getHistory(paperId) {
    return api.get(`/api/qa/${paperId}/history`)
  },
}

export const reportsAPI = {
  generate(paperId, reportType) {
    return api.post(`/api/reports/${paperId}`, { report_type: reportType })
  },

  /**
   * 流式生成报告。onDelta 收到累积报告文本。
   * 返回 { content }；出错抛带 userMessage 的 Error。
   */
  async generateStream(paperId, reportType, { onDelta } = {}) {
    let content = ''
    let streamError = null
    await streamSSE(`/api/reports/${paperId}/stream`, { report_type: reportType }, (evt) => {
      if (evt.type === 'delta') {
        content += evt.content || ''
        onDelta?.(content)
      } else if (evt.type === 'error') {
        streamError = evt.message || '报告生成失败，请重试'
      }
    })
    if (streamError) {
      const err = new Error(streamError)
      err.userMessage = streamError
      throw err
    }
    return { content }
  },

  getReports(paperId) {
    return api.get(`/api/reports/${paperId}`)
  },

  /**
   * 跨论文对比（功能 A）。onTable 收到表格数据（首帧），onDelta 收到累积综述文本。
   * 返回 { table, content }；出错抛带 userMessage 的 Error。
   */
  async compareStream(paperIds, view, { onTable, onDelta } = {}) {
    let table = null
    let content = ''
    let streamError = null
    await streamSSE('/api/reports/comparison', { paper_ids: paperIds, view }, (evt) => {
      if (evt.type === 'table') {
        table = evt.table || null
        onTable?.(table)
      } else if (evt.type === 'delta') {
        content += evt.content || ''
        onDelta?.(content)
      } else if (evt.type === 'error') {
        streamError = evt.message || '对比生成失败，请重试'
      }
    })
    if (streamError) {
      const err = new Error(streamError)
      err.userMessage = streamError
      throw err
    }
    return { table, content }
  },
}

export const searchAPI = {
  // 学术搜索：联网检索 + 综述 + 主题图表。返回 { answer, notice, sources, chart, page, query_used }
  query(q, page = 1, sort = 'citation') {
    return api.post('/api/search', { query: q, page, sort })
  },
  // 把开放获取论文加入知识库（单篇/批量）。返回 { added, failed }
  addToLibrary(papers) {
    return api.post('/api/search/add-to-library', { papers })
  },
}

export default api
