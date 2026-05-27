import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSources, getBatches, uploadFile } from '../api'
import type { DataSource, ImportBatch } from '../types'
import { format } from 'date-fns'
import clsx from 'clsx'

const STATUS_BADGE: Record<string, string> = {
  COMPLETED: 'bg-green-100 text-green-800',
  FAILED: 'bg-red-100 text-red-800',
  PROCESSING: 'bg-blue-100 text-blue-800',
  PENDING: 'bg-gray-100 text-gray-700',
}

export default function Upload() {
  const qc = useQueryClient()
  const [selectedSource, setSelectedSource] = useState<string>('')
  const [dragging, setDragging] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [lastResult, setLastResult] = useState<ImportBatch | null>(null)
  const [expandedBatch, setExpandedBatch] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const { data: sources = [] } = useQuery({ queryKey: ['sources'], queryFn: getSources })
  const { data: batches = [] } = useQuery({
    queryKey: ['batches'],
    queryFn: getBatches,
    refetchInterval: 5000,
  })

  const mutation = useMutation({
    mutationFn: ({ sourceId, file }: { sourceId: string; file: File }) =>
      uploadFile(sourceId, file),
    onSuccess: (result) => {
      setLastResult(result)
      setUploadError('')
      qc.invalidateQueries({ queryKey: ['batches'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (err: { response?: { data?: { error?: string } } }) => {
      setUploadError(err?.response?.data?.error || 'Upload failed')
    },
  })

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) doUpload(file)
  }

  const doUpload = (file: File) => {
    if (!selectedSource) {
      setUploadError('Select a data source first.')
      return
    }
    setUploadError('')
    setLastResult(null)
    mutation.mutate({ sourceId: selectedSource, file })
  }

  const selectedSourceObj = sources.find((s: DataSource) => s.id === selectedSource)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Upload Data</h1>
        <p className="mt-0.5 text-sm text-gray-500">
          Upload a file to ingest and normalize. Rows are automatically flagged for review.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload panel */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Data source</label>
            <select
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              <option value="">Select a source…</option>
              {sources.map((s: DataSource) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {selectedSourceObj && (
            <div className="text-xs text-gray-500 bg-gray-50 rounded-lg p-3 border border-gray-100">
              {selectedSourceObj.description}
            </div>
          )}

          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={clsx(
              'border-2 border-dashed rounded-xl px-6 py-10 text-center cursor-pointer transition-colors',
              dragging ? 'border-green-400 bg-green-50' : 'border-gray-200 hover:border-gray-300 bg-white'
            )}
          >
            <p className="text-3xl mb-2">📂</p>
            <p className="text-sm font-medium text-gray-700">Drop file here or click to browse</p>
            <p className="text-xs text-gray-400 mt-1">Accepts .txt, .csv files</p>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.txt,.xls,.xlsx"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) doUpload(f)
                e.target.value = ''
              }}
            />
          </div>

          {mutation.isPending && (
            <div className="bg-blue-50 text-blue-700 text-sm rounded-lg px-4 py-3">
              Processing file…
            </div>
          )}

          {uploadError && (
            <div className="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3">{uploadError}</div>
          )}

          {lastResult && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <p className="text-sm font-medium text-green-800 mb-2">
                Upload complete: {lastResult.file_name}
              </p>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-white rounded p-2 text-center">
                  <div className="text-lg font-bold text-gray-900">{lastResult.total_rows}</div>
                  <div className="text-gray-500">Total rows</div>
                </div>
                <div className="bg-white rounded p-2 text-center">
                  <div className="text-lg font-bold text-green-700">{lastResult.success_rows}</div>
                  <div className="text-gray-500">Success</div>
                </div>
                <div className="bg-white rounded p-2 text-center">
                  <div className="text-lg font-bold text-amber-600">{lastResult.warning_rows}</div>
                  <div className="text-gray-500">Flagged</div>
                </div>
                <div className="bg-white rounded p-2 text-center">
                  <div className="text-lg font-bold text-red-600">{lastResult.error_rows}</div>
                  <div className="text-gray-500">Errors</div>
                </div>
              </div>
              {lastResult.error_rows > 0 && (
                <p className="mt-2 text-xs text-amber-700">
                  {lastResult.error_rows} rows had parse errors — see batch history for details.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Batch history */}
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Import History</h2>
          {batches.length === 0 ? (
            <p className="text-sm text-gray-400">No uploads yet.</p>
          ) : (
            <div className="space-y-2">
              {batches.slice(0, 20).map((b: ImportBatch) => (
                <div key={b.id} className="bg-white border border-gray-200 rounded-lg p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900 truncate max-w-[200px]">
                        {b.file_name}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {b.source_name} · {format(new Date(b.started_at), 'MMM d, HH:mm')}
                      </p>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[b.status]}`}>
                      {b.status_display}
                    </span>
                  </div>
                  {b.status === 'COMPLETED' && (
                    <div className="mt-2 flex gap-3 text-xs text-gray-500">
                      <span>{b.total_rows} rows</span>
                      <span className="text-green-700">{b.success_rows} ok</span>
                      {b.warning_rows > 0 && <span className="text-amber-600">{b.warning_rows} flagged</span>}
                      {b.error_rows > 0 && (
                        <button
                          onClick={() => setExpandedBatch(expandedBatch === b.id ? null : b.id)}
                          className="text-red-600 underline"
                        >
                          {b.error_rows} errors
                        </button>
                      )}
                    </div>
                  )}
                  {expandedBatch === b.id && b.error_details?.length > 0 && (
                    <div className="mt-2 bg-red-50 rounded p-2 max-h-32 overflow-y-auto">
                      {b.error_details.map((e, i) => (
                        <p key={i} className="text-xs text-red-700">
                          Row {e.row}: {e.error}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
