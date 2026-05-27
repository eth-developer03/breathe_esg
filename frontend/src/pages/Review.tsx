import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRecords, approveRecord, rejectRecord, bulkApprove, getRecordAudit } from '../api'
import type { RecordFilters } from '../api'
import type { NormalizedRecord, AuditEvent } from '../types'
import { format } from 'date-fns'
import clsx from 'clsx'

const STATUS_BADGE: Record<string, string> = {
  PENDING: 'bg-gray-100 text-gray-700',
  APPROVED: 'bg-green-100 text-green-800',
  REJECTED: 'bg-red-100 text-red-800',
  FLAGGED: 'bg-amber-100 text-amber-800',
}

const SCOPE_BADGE: Record<number, string> = {
  1: 'bg-orange-100 text-orange-700',
  2: 'bg-blue-100 text-blue-700',
  3: 'bg-purple-100 text-purple-700',
}

const FLAG_SHORT: Record<string, string> = {
  ZERO_QUANTITY: 'Zero qty',
  NEGATIVE_QUANTITY: 'Negative',
  FUTURE_DATE: 'Future date',
  STALE_DATE: 'Stale date',
  UNKNOWN_FACILITY: 'Unknown facility',
  STATISTICAL_OUTLIER: 'Outlier',
  MISSING_EMISSION_FACTOR: 'No EF',
  DUPLICATE_CANDIDATE: 'Duplicate?',
  PERIOD_GAP: 'Period gap',
}

function RecordDrawer({
  record,
  onClose,
  onApprove,
  onReject,
}: {
  record: NormalizedRecord
  onClose: () => void
  onApprove: (id: string, notes: string) => void
  onReject: (id: string, notes: string) => void
}) {
  const [notes, setNotes] = useState('')
  const [rejectNotes, setRejectNotes] = useState('')
  const [showReject, setShowReject] = useState(false)
  const [tab, setTab] = useState<'detail' | 'raw' | 'audit'>('detail')

  const { data: auditEvents = [] } = useQuery<AuditEvent[]>({
    queryKey: ['audit', record.id],
    queryFn: () => getRecordAudit(record.id),
    enabled: tab === 'audit',
  })

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-white shadow-xl flex flex-col h-full overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div>
            <p className="font-semibold text-gray-900">{record.category_display}</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {record.facility_name || record.facility_code} · {record.activity_date}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl leading-none">&times;</button>
        </div>

        <div className="flex border-b border-gray-200 px-5">
          {(['detail', 'raw', 'audit'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={clsx(
                'py-2.5 text-sm font-medium mr-4 border-b-2 -mb-px',
                tab === t
                  ? 'border-green-600 text-green-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {tab === 'detail' && (
            <>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Field label="Scope" value={
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${SCOPE_BADGE[record.scope]}`}>
                    {record.scope_display}
                  </span>
                } />
                <Field label="Status" value={
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[record.status]}`}>
                    {record.status_display}
                  </span>
                } />
                <Field label="Source" value={record.source_type} />
                <Field label="Category" value={record.category_display} />
                <Field label="Activity Date" value={record.activity_date} />
                {record.period_start && (
                  <Field label="Billing Period"
                    value={`${record.period_start} → ${record.period_end}`} />
                )}
                <Field label="Facility" value={`${record.facility_name || '—'} (${record.facility_code})`} />
                <Field label="Country" value={record.country || '—'} />
                <Field label="Quantity (raw)" value={`${record.raw_quantity} ${record.raw_unit}`} />
                <Field label="Quantity (normalised)"
                  value={`${parseFloat(record.normalized_quantity).toLocaleString()} ${record.normalized_unit}`} />
                <Field label="Vendor" value={record.vendor || '—'} />
                <Field label="Description" value={record.description || '—'} />
              </div>

              {record.emission_factor_display && (
                <div className="bg-gray-50 rounded-lg p-3 text-xs">
                  <p className="font-medium text-gray-700 mb-1">Emission Factor</p>
                  <p className="text-gray-600">
                    {record.emission_factor_display.factor} kgCO₂e / {record.emission_factor_display.unit}
                    &nbsp;·&nbsp; {record.emission_factor_display.source} ({record.emission_factor_display.year})
                  </p>
                </div>
              )}

              {record.co2e_kg && (
                <div className="bg-green-50 rounded-lg p-3 text-center">
                  <p className="text-xs text-gray-500 mb-0.5">Estimated CO₂e</p>
                  <p className="text-2xl font-bold text-green-700">
                    {(parseFloat(record.co2e_kg) / 1000).toFixed(3)} tCO₂e
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{parseFloat(record.co2e_kg).toFixed(2)} kgCO₂e</p>
                </div>
              )}

              {record.flags.length > 0 && (
                <div className="bg-amber-50 rounded-lg p-3">
                  <p className="text-xs font-medium text-amber-800 mb-2">Quality Flags</p>
                  <div className="flex flex-wrap gap-1.5">
                    {record.flags.map((f) => (
                      <span key={f} className="text-xs bg-amber-100 text-amber-800 rounded px-2 py-0.5">
                        {FLAG_SHORT[f] || f}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {record.was_edited && record.original_values && (
                <div className="bg-blue-50 rounded-lg p-3 text-xs">
                  <p className="font-medium text-blue-800 mb-1">Edited by analyst (original values)</p>
                  {Object.entries(record.original_values).map(([k, v]) => (
                    <div key={k} className="text-blue-700">{k}: {v}</div>
                  ))}
                </div>
              )}

              {record.reviewed_by_name && (
                <div className="text-xs text-gray-400">
                  {record.status_display} by {record.reviewed_by_name}
                  {record.reviewed_at && ` on ${format(new Date(record.reviewed_at), 'MMM d, yyyy HH:mm')}`}
                  {record.review_notes && ` — "${record.review_notes}"`}
                </div>
              )}
            </>
          )}

          {tab === 'raw' && (
            <div className="text-xs font-mono bg-gray-50 rounded p-3 overflow-x-auto whitespace-pre-wrap break-all">
              Row {record.raw_row_number} · Original data as ingested
            </div>
          )}

          {tab === 'audit' && (
            <div className="space-y-2">
              {auditEvents.length === 0 ? (
                <p className="text-sm text-gray-400">No audit events.</p>
              ) : auditEvents.map((e) => (
                <div key={e.id} className="border border-gray-100 rounded-lg p-3 text-xs">
                  <div className="flex justify-between">
                    <span className="font-medium text-gray-900">{e.event_type_display}</span>
                    <span className="text-gray-400">{format(new Date(e.timestamp), 'MMM d, HH:mm')}</span>
                  </div>
                  <span className="text-gray-500">by {e.user_name}</span>
                  {e.notes && <p className="mt-1 text-gray-600 italic">"{e.notes}"</p>}
                </div>
              ))}
            </div>
          )}
        </div>

        {record.status !== 'APPROVED' && record.status !== 'REJECTED' && (
          <div className="px-5 py-4 border-t border-gray-200 space-y-3">
            {!showReject ? (
              <>
                <input
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Optional approval notes…"
                  className="w-full border border-gray-200 rounded px-3 py-2 text-sm"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => onApprove(record.id, notes)}
                    className="flex-1 bg-green-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-green-700"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => setShowReject(true)}
                    className="flex-1 border border-red-300 text-red-600 rounded-lg py-2 text-sm font-medium hover:bg-red-50"
                  >
                    Reject
                  </button>
                </div>
              </>
            ) : (
              <>
                <textarea
                  value={rejectNotes}
                  onChange={(e) => setRejectNotes(e.target.value)}
                  placeholder="Rejection reason (required)…"
                  rows={3}
                  className="w-full border border-gray-200 rounded px-3 py-2 text-sm"
                />
                <div className="flex gap-2">
                  <button
                    disabled={!rejectNotes.trim()}
                    onClick={() => onReject(record.id, rejectNotes)}
                    className="flex-1 bg-red-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-red-700 disabled:opacity-50"
                  >
                    Confirm Reject
                  </button>
                  <button
                    onClick={() => setShowReject(false)}
                    className="px-4 border border-gray-200 text-gray-600 rounded-lg py-2 text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm text-gray-900 mt-0.5">{value}</p>
    </div>
  )
}

export default function Review() {
  const qc = useQueryClient()
  const [filters, setFilters] = useState<RecordFilters>({ ordering: '-activity_date' })
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [activeRecord, setActiveRecord] = useState<NormalizedRecord | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['records', filters, page],
    queryFn: () => getRecords({ ...filters, page }),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['records'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    setActiveRecord(null)
  }

  const approveMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) => approveRecord(id, notes),
    onSuccess: invalidate,
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) => rejectRecord(id, notes),
    onSuccess: invalidate,
  })

  const bulkMutation = useMutation({
    mutationFn: () => bulkApprove(Array.from(selected)),
    onSuccess: () => { setSelected(new Set()); invalidate() },
  })

  const records = data?.results || []
  const total = data?.count || 0

  const setFilter = (key: keyof RecordFilters, value: string | number | boolean | undefined) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }))
    setPage(1)
    setSelected(new Set())
  }

  const toggleSelect = (id: string) => {
    setSelected((prev: Set<string>) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  const selectAll = () => {
    const reviewable = records.filter((r) => r.status === 'PENDING' || r.status === 'FLAGGED')
    setSelected(new Set(reviewable.map((r) => r.id)))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Review</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {total.toLocaleString()} record{total !== 1 ? 's' : ''} · click a row to review
          </p>
        </div>
        {selected.size > 0 && (
          <button
            onClick={() => bulkMutation.mutate()}
            disabled={bulkMutation.isPending}
            className="bg-green-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-green-700 disabled:opacity-50"
          >
            Approve {selected.size} selected
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <select
          value={filters.status || ''}
          onChange={(e) => setFilter('status', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
        >
          <option value="">All statuses</option>
          <option value="PENDING">Pending</option>
          <option value="FLAGGED">Flagged</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>

        <select
          value={filters.scope || ''}
          onChange={(e) => setFilter('scope', e.target.value ? Number(e.target.value) : undefined)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
        >
          <option value="">All scopes</option>
          <option value="1">Scope 1</option>
          <option value="2">Scope 2</option>
          <option value="3">Scope 3</option>
        </select>

        <select
          value={filters.source_type || ''}
          onChange={(e) => setFilter('source_type', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
        >
          <option value="">All sources</option>
          <option value="SAP">SAP</option>
          <option value="UTILITY">Utility</option>
          <option value="TRAVEL">Travel</option>
        </select>

        <select
          value={filters.flag || ''}
          onChange={(e) => setFilter('flag', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
        >
          <option value="">All flags</option>
          <option value="STATISTICAL_OUTLIER">Outlier</option>
          <option value="MISSING_EMISSION_FACTOR">No EF</option>
          <option value="DUPLICATE_CANDIDATE">Duplicate?</option>
          <option value="UNKNOWN_FACILITY">Unknown Facility</option>
          <option value="PERIOD_GAP">Period Gap</option>
        </select>

        <input
          type="date"
          value={filters.date_from || ''}
          onChange={(e) => setFilter('date_from', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          placeholder="From date"
        />
        <input
          type="date"
          value={filters.date_to || ''}
          onChange={(e) => setFilter('date_to', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
        />

        <input
          type="text"
          value={filters.search || ''}
          onChange={(e) => setFilter('search', e.target.value)}
          placeholder="Search facility, vendor…"
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white min-w-[180px]"
        />

        {Object.values(filters).some(Boolean) && (
          <button
            onClick={() => { setFilters({ ordering: '-activity_date' }); setPage(1) }}
            className="text-sm text-gray-500 hover:text-gray-900 px-2"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-3 py-2.5 text-left w-8">
                  <input
                    type="checkbox"
                    checked={selected.size > 0 && selected.size === records.filter(r => r.status === 'PENDING' || r.status === 'FLAGGED').length}
                    onChange={selectAll}
                    className="rounded"
                  />
                </th>
                <th className="px-3 py-2.5 text-left font-medium text-gray-600">Date</th>
                <th className="px-3 py-2.5 text-left font-medium text-gray-600">Scope</th>
                <th className="px-3 py-2.5 text-left font-medium text-gray-600">Category</th>
                <th className="px-3 py-2.5 text-left font-medium text-gray-600">Facility</th>
                <th className="px-3 py-2.5 text-right font-medium text-gray-600">Qty</th>
                <th className="px-3 py-2.5 text-right font-medium text-gray-600">CO₂e (kg)</th>
                <th className="px-3 py-2.5 text-left font-medium text-gray-600">Flags</th>
                <th className="px-3 py-2.5 text-left font-medium text-gray-600">Status</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={9} className="text-center py-8 text-gray-400">Loading…</td></tr>
              )}
              {!isLoading && records.length === 0 && (
                <tr><td colSpan={9} className="text-center py-8 text-gray-400">No records match these filters.</td></tr>
              )}
              {records.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setActiveRecord(r)}
                  className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer"
                >
                  <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                    {(r.status === 'PENDING' || r.status === 'FLAGGED') && (
                      <input
                        type="checkbox"
                        checked={selected.has(r.id)}
                        onChange={() => toggleSelect(r.id)}
                        className="rounded"
                      />
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-gray-700 whitespace-nowrap">{r.activity_date}</td>
                  <td className="px-3 py-2.5">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${SCOPE_BADGE[r.scope]}`}>
                      S{r.scope}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-gray-700">{r.category_display}</td>
                  <td className="px-3 py-2.5 text-gray-700 max-w-[180px] truncate">
                    {r.facility_name || r.facility_code || '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-900 font-mono">
                    {parseFloat(r.normalized_quantity).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    <span className="text-gray-400 text-xs ml-1">{r.normalized_unit}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-900 font-mono">
                    {r.co2e_kg ? parseFloat(r.co2e_kg).toFixed(1) : '—'}
                  </td>
                  <td className="px-3 py-2.5">
                    {r.flags.length > 0 && (
                      <div className="flex gap-1 flex-wrap">
                        {r.flags.slice(0, 2).map((f) => (
                          <span key={f} className="text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded px-1.5">
                            {FLAG_SHORT[f] || f}
                          </span>
                        ))}
                        {r.flags.length > 2 && (
                          <span className="text-xs text-gray-400">+{r.flags.length - 2}</span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[r.status]}`}>
                      {r.status_display}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 50 && (
          <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between text-sm">
            <span className="text-gray-500">
              Showing {Math.min((page - 1) * 50 + 1, total)}–{Math.min(page * 50, total)} of {total.toLocaleString()}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 border border-gray-200 rounded text-gray-700 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page * 50 >= total}
                className="px-3 py-1 border border-gray-200 rounded text-gray-700 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {activeRecord && (
        <RecordDrawer
          record={activeRecord}
          onClose={() => setActiveRecord(null)}
          onApprove={(id, notes) => approveMutation.mutate({ id, notes })}
          onReject={(id, notes) => rejectMutation.mutate({ id, notes })}
        />
      )}
    </div>
  )
}
