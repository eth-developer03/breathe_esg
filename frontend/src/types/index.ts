export interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  org_id: string
  org_name: string
  role: 'admin' | 'analyst' | 'viewer'
}

export interface DataSource {
  id: string
  name: string
  source_type: 'SAP' | 'UTILITY' | 'TRAVEL'
  source_type_display: string
  description: string
  config: Record<string, unknown>
  created_at: string
}

export interface ImportBatch {
  id: string
  source_name: string
  source_type: string
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED'
  status_display: string
  file_name: string
  uploaded_by_name: string | null
  started_at: string
  completed_at: string | null
  total_rows: number
  success_rows: number
  error_rows: number
  warning_rows: number
  error_details: Array<{ row: number; error: string }>
}

export interface EmissionFactorDisplay {
  category: string
  factor: string
  unit: string
  source: string
  year: number
}

export type RecordStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'FLAGGED'
export type RecordScope = 1 | 2 | 3

export interface NormalizedRecord {
  id: string
  source_type: 'SAP' | 'UTILITY' | 'TRAVEL'
  scope: RecordScope
  scope_display: string
  category: string
  category_display: string
  activity_date: string
  period_start: string | null
  period_end: string | null
  facility_code: string
  facility_name: string
  country: string
  raw_quantity: string
  raw_unit: string
  normalized_quantity: string
  normalized_unit: string
  vendor: string
  description: string
  emission_factor_display: EmissionFactorDisplay | null
  co2e_kg: string | null
  was_edited: boolean
  original_values: Record<string, string> | null
  status: RecordStatus
  status_display: string
  flags: string[]
  reviewed_by_name: string | null
  reviewed_at: string | null
  review_notes: string
  created_at: string
  updated_at: string
  raw_row_number: number | null
}

export interface DashboardStats {
  total_records: number
  status_breakdown: {
    pending: number
    approved: number
    rejected: number
    flagged: number
  }
  scope_co2e_kg: Array<{ scope: number; co2e_kg: number | null }>
  source_breakdown: Array<{ source_type: string; count: number; co2e_kg: number | null }>
  flag_breakdown: Record<string, number>
  total_co2e_kg: number
}

export interface AuditEvent {
  id: string
  event_type: string
  event_type_display: string
  user_name: string
  before_state: Record<string, unknown>
  after_state: Record<string, unknown>
  notes: string
  timestamp: string
}

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
