import { defineStore } from 'pinia'
import { ref } from 'vue'
import { papersAPI, qaAPI, reportsAPI } from '@/api'
import { savePDF, getPDFUrl, hasPDF, deletePDF } from '@/utils/pdfStorage'
export const usePapersStore = defineStore('papers', () => {
  const papers = ref([])
  const currentPaper = ref(null)
  const loading = ref(false)
  const uploading = ref(false)
  const pollingPaperId = ref(null)
  const pdfCache = ref(new Map())
  let pollInterval = null

  function startPolling(paperId) {
    stopPolling()
    pollingPaperId.value = paperId
    pollInterval = setInterval(async () => {
      try {
        const response = await papersAPI.get(paperId)
        const index = papers.value.findIndex((p) => p.paper_id === paperId)
        if (index !== -1) {
          papers.value[index] = response.items || response
        }
        if (currentPaper.value?.paper_id === paperId) {
          currentPaper.value = response.items || response
        }
        const status = (response.items || response).parse_status
        if (status === 'completed' || status === 'failed') {
          stopPolling()
        }
      } catch (error) {
        console.error('Polling error:', error)
      }
    }, 3000)
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
    pollingPaperId.value = null
  }

  function cachePdf(paperId, file) {
    const blobUrl = URL.createObjectURL(file)
    pdfCache.value.set(paperId, blobUrl)
    return blobUrl
  }

  function getCachedPdf(paperId) {
    return pdfCache.value.get(paperId) || null
  }

  function clearPdfCache(paperId) {
    const url = pdfCache.value.get(paperId)
    if (url) {
      URL.revokeObjectURL(url)
    }
    pdfCache.value.delete(paperId)
  }

  function clearAllPdfCache() {
    pdfCache.value.forEach((url) => {
      URL.revokeObjectURL(url)
    })
    pdfCache.value.clear()
  }

  async function fetchPdf(paperId) {
    const cached = pdfCache.value.get(paperId)
    if (cached) {
      console.log('fetchPdf: using memory cache')
      return cached
    }

    const url = await getPDFUrl(paperId)
    if (url) {
      console.log('fetchPdf: loaded from IndexedDB')
      pdfCache.value.set(paperId, url)
      return url
    }

    return null
  }

  async function fetchPapers() {
    loading.value = true
    try {
      const response = await papersAPI.list()
      papers.value = response.items || response
    } catch (error) {
      console.error('Failed to fetch papers:', error)
    } finally {
      loading.value = false
    }
  }
  async function uploadPaper(file) {
    uploading.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await papersAPI.upload(formData)

      const paperId = response.paper_id || response.paperId
      if (paperId) {
        await savePDF(paperId, file)
      }

      await fetchPapers()

      if (response.paper_id) {
        startPolling(response.paper_id)
      }

      return response
    } catch (error) {
      throw error
    } finally {
      uploading.value = false
    }
  }
  async function reloadPdfFromFile(paperId, file) {
    cachePdf(paperId, file)
    await savePDF(paperId, file)
    return pdfCache.value.get(paperId)
  }

  async function getPaper(paperId) {
    loading.value = true
    try {
      const response = await papersAPI.get(paperId)
      currentPaper.value = response.items || response
      return currentPaper.value
    } catch (error) {
      throw error
    } finally {
      loading.value = false
    }
  }
  async function updatePaper(paperId, data) {
    try {
      const response = await papersAPI.update(paperId, data)
      const index = papers.value.findIndex((p) => p.paper_id === paperId)
      if (index !== -1) {
        papers.value[index] = { ...papers.value[index], ...response }
      }
      if (currentPaper.value?.paper_id === paperId) {
        currentPaper.value = { ...currentPaper.value, ...response }
      }
      return response
    } catch (error) {
      throw error
    }
  }
  async function deletePaper(paperId) {
    try {
      await papersAPI.delete(paperId)
      papers.value = papers.value.filter((p) => p.paper_id !== paperId)
      if (currentPaper.value?.paper_id === paperId) {
        currentPaper.value = null
      }
      clearPdfCache(paperId)
      await deletePDF(paperId)
    } catch (error) {
      throw error
    }
  }
  async function reparsePaper(paperId) {
    try {
      await papersAPI.reparse(paperId)
      await fetchPapers()
      startPolling(paperId)
    } catch (error) {
      throw error
    }
  }
  return {
    papers,
    currentPaper,
    loading,
    uploading,
    pollingPaperId,
    fetchPapers,
    uploadPaper,
    getPaper,
    updatePaper,
    deletePaper,
    reparsePaper,
    startPolling,
    stopPolling,
    cachePdf,
    getCachedPdf,
    clearPdfCache,
    clearAllPdfCache,
    fetchPdf,
    reloadPdfFromFile,
  }
})
export const useQAStore = defineStore('qa', () => {
  const conversations = ref({})
  const currentQuestion = ref('')
  const answering = ref(false)
  async function askQuestion(paperId, question, conversationId = null) {
    answering.value = true
    try {
      const response = await qaAPI.ask(paperId, question, conversationId)
      if (!conversations.value[paperId]) {
        conversations.value[paperId] = []
      }
      conversations.value[paperId].push({
        question,
        answer: response.answer,
        sources: response.sources || [],
        timestamp: new Date().toISOString(),
      })
      return response
    } catch (error) {
      throw error
    } finally {
      answering.value = false
    }
  }
  async function askQuestionStream(paperId, question, callbacks = {}) {
    answering.value = true
    try {
      const result = await qaAPI.askStream(paperId, question, callbacks)
      if (!conversations.value[paperId]) {
        conversations.value[paperId] = []
      }
      conversations.value[paperId].push({
        question,
        answer: result.answer,
        sources: result.sources || [],
        timestamp: new Date().toISOString(),
      })
      return result
    } finally {
      answering.value = false
    }
  }
  async function getConversationHistory(paperId) {
    try {
      const response = await qaAPI.getHistory(paperId)
      conversations.value[paperId] = response.conversations || response.items || response
      return conversations.value[paperId]
    } catch (error) {
      throw error
    }
  }
  function clearConversation(paperId) {
    conversations.value[paperId] = []
  }
  return {
    conversations,
    currentQuestion,
    answering,
    askQuestion,
    askQuestionStream,
    getConversationHistory,
    clearConversation,
  }
})
export const useReportsStore = defineStore('reports', () => {
  const reports = ref({})
  const generating = ref(false)
  async function generateReport(paperId, reportType) {
    generating.value = true
    try {
      const response = await reportsAPI.generate(paperId, reportType)
      if (!reports.value[paperId]) {
        reports.value[paperId] = {}
      }
      reports.value[paperId][reportType] = response.content
      return response.content
    } catch (error) {
      throw error
    } finally {
      generating.value = false
    }
  }
  async function generateReportStream(paperId, reportType, callbacks = {}) {
    generating.value = true
    try {
      const { content } = await reportsAPI.generateStream(paperId, reportType, callbacks)
      if (!reports.value[paperId]) {
        reports.value[paperId] = {}
      }
      reports.value[paperId][reportType] = content
      return content
    } finally {
      generating.value = false
    }
  }
  function getReport(paperId, reportType) {
    return reports.value[paperId]?.[reportType]
  }

  async function getReports(paperId) {
    const response = await reportsAPI.getReports(paperId)
    const list = response.reports || []
    if (!reports.value[paperId]) reports.value[paperId] = {}
    for (const r of list) {
      reports.value[paperId][r.report_type] = r.content
    }
    return reports.value[paperId]
  }

  return {
    reports,
    generating,
    generateReport,
    generateReportStream,
    getReport,
    getReports,
  }
})
