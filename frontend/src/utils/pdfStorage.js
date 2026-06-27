import { openDB } from 'idb'

const DB_NAME = 'PDFStorage'
const STORE_NAME = 'pdfs'
const DB_VERSION = 1

const dbPromise = openDB(DB_NAME, DB_VERSION, {
  upgrade(db) {
    if (!db.objectStoreNames.contains(STORE_NAME)) {
      db.createObjectStore(STORE_NAME, { keyPath: 'paperId' })
    }
  },
})

export async function savePDF(paperId, file) {
  try {
    const db = await dbPromise
    const arrayBuffer = await file.arrayBuffer()
    
    await db.put(STORE_NAME, {
      paperId,
      data: arrayBuffer,
      name: file.name,
      size: file.size,
      type: file.type,
      savedAt: Date.now(),
    })
    
    console.log(`✅ PDF 已缓存: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`)
    return true
  } catch (error) {
    console.error('❌ 保存 PDF 失败:', error)
    return false
  }
}

export async function getPDF(paperId) {
  try {
    const db = await dbPromise
    return await db.get(STORE_NAME, paperId)
  } catch (error) {
    console.error('❌ 获取 PDF 失败:', error)
    return null
  }
}

export async function getPDFUrl(paperId) {
  const record = await getPDF(paperId)
  if (!record) return null
  
  const blob = new Blob([record.data], { type: 'application/pdf' })
  return URL.createObjectURL(blob)
}

export async function hasPDF(paperId) {
  const record = await getPDF(paperId)
  return record !== undefined && record !== null
}

export async function deletePDF(paperId) {
  try {
    const db = await dbPromise
    await db.delete(STORE_NAME, paperId)
    console.log(`🗑️ PDF 已删除: ${paperId}`)
    return true
  } catch (error) {
    console.error('❌ 删除 PDF 失败:', error)
    return false
  }
}

export async function getAllPDFs() {
  try {
    const db = await dbPromise
    return await db.getAll(STORE_NAME)
  } catch (error) {
    console.error('❌ 获取列表失败:', error)
    return []
  }
}

export async function clearAllPDFs() {
  try {
    const db = await dbPromise
    await db.clear(STORE_NAME)
    console.log('🗑️ 所有 PDF 已清除')
    return true
  } catch (error) {
    console.error('❌ 清除失败:', error)
    return false
  }
}
