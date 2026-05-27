import client from './client'
import type {
  User, DataSource, ImportBatch, NormalizedRecord,
  DashboardStats, AuditEvent, PaginatedResponse
} from '../types'

// Auth
export const login = async (username: string, password: string) => {
  const { data } = await client.post('/auth/token/', { username, password })
  localStorage.setItem('access_token', data.access)
  localStorage.setItem('refresh_token', data.refresh)
  return data
}

export const logout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export const getMe = async (): Promise<User> => {
  const { data } = await client.get('/me/')
  return data
}

// Dashboard
export const getDashboard = async (): Promise<DashboardStats> => {
  const { data } = await client.get('/dashboard/')
  return data
}

// Sources
export const getSources = async (): Promise<DataSource[]> => {
  const { data } = await client.get('/sources/')
  return data
}

// Batches
export const getBatches = async (): Promise<ImportBatch[]> => {
  const { data } = await client.get('/batches/')
  return data.results ?? data
}

export const uploadFile = async (sourceId: string, file: File): Promise<ImportBatch> => {
  const form = new FormData()
  form.append('source_id', sourceId)
  form.append('file', file)
  const { data } = await client.post('/upload/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// Records
export interface RecordFilters {
  status?: string
  scope?: number
  source_type?: string
  category?: string
  date_from?: string
  date_to?: string
  has_flags?: boolean
  flag?: string
  search?: string
  ordering?: string
  page?: number
}

export const getRecords = async (filters: RecordFilters = {}): Promise<PaginatedResponse<NormalizedRecord>> => {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== '' && v !== null)
  )
  const { data } = await client.get('/records/', { params })
  return data
}

export const getRecord = async (id: string): Promise<NormalizedRecord> => {
  const { data } = await client.get(`/records/${id}/`)
  return data
}

export const approveRecord = async (id: string, notes?: string): Promise<NormalizedRecord> => {
  const { data } = await client.post(`/records/${id}/approve/`, { notes })
  return data
}

export const rejectRecord = async (id: string, notes: string): Promise<NormalizedRecord> => {
  const { data } = await client.post(`/records/${id}/reject/`, { notes })
  return data
}

export const editRecord = async (
  id: string,
  fields: Partial<NormalizedRecord> & { reason: string }
): Promise<NormalizedRecord> => {
  const { data } = await client.patch(`/records/${id}/`, fields)
  return data
}

export const bulkApprove = async (ids: string[]): Promise<{ approved: number; ids: string[] }> => {
  const { data } = await client.post('/records/bulk-approve/', { ids })
  return data
}

export const getRecordAudit = async (id: string): Promise<AuditEvent[]> => {
  const { data } = await client.get(`/records/${id}/audit/`)
  return data
}

export const getAuditLog = async (): Promise<AuditEvent[]> => {
  const { data } = await client.get('/audit-log/')
  return data
}
