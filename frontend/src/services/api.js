/*
 * Centralized MarketIQ API client.
 * Backend source of truth: backend/app/api/*. Endpoints and payloads below
 * mirror the FastAPI routes exactly - do not invent endpoints or fields.
 */
import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  // Research POST is synchronous on the backend (Phase 3) and can take a while.
  timeout: 180000,
})

// ----------------------------- Health & stats -----------------------------
export async function getHealth() {
  const { data } = await http.get('/health')
  return data
}

export async function getStats() {
  const { data } = await http.get('/stats')
  return data
}

// -------------------------------- Research --------------------------------
export const researchApi = {
  async create({ query, researchType = 'market_analysis', documentIds = [] }) {
    const payload = {
      query,
      research_type: researchType,
      document_ids: documentIds.length ? documentIds : undefined,
    }
    const { data } = await http.post('/research', payload)
    return data
  },

  async get(id) {
    const { data } = await http.get(`/research/${id}`)
    return data
  },

  async recent(limit = 10) {
    const { data } = await http.get('/research/recent', { params: { limit } })
    return data
  },
}

// ------------------------------- Documents --------------------------------
export const documentsApi = {
  async list() {
    const { data } = await http.get('/documents')
    return data
  },

  async get(id) {
    const { data } = await http.get(`/documents/${id}`)
    return data
  },

  async upload(file) {
    const form = new FormData()
    form.append('file', file)
    const { data } = await http.post('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async remove(id) {
    const { data } = await http.delete(`/documents/${id}`)
    return data
  },

  async search({ query, topK = 5, documentIds = [] }) {
    const payload = { query, top_k: topK }
    if (documentIds.length) payload.document_ids = documentIds
    const { data } = await http.post('/documents/search', payload)
    return data
  },
}

// ------------------------- Backward-compatible aliases --------------------
export const createResearch = (options) => researchApi.create(options)
export const getResearch = (id) => researchApi.get(id)
export const getRecentResearch = (limit = 10) => researchApi.recent(limit)

export default http