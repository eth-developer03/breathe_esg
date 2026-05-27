import { useQuery } from '@tanstack/react-query'
import { getDashboard } from '../api'

const SCOPE_COLORS: Record<number, string> = {
  1: 'bg-orange-100 text-orange-800',
  2: 'bg-blue-100 text-blue-800',
  3: 'bg-purple-100 text-purple-800',
}

const SOURCE_LABELS: Record<string, string> = {
  SAP: 'SAP Fuel & Procurement',
  UTILITY: 'Utility Electricity',
  TRAVEL: 'Corporate Travel',
}

const FLAG_LABELS: Record<string, string> = {
  ZERO_QUANTITY: 'Zero Quantity',
  NEGATIVE_QUANTITY: 'Negative Quantity',
  FUTURE_DATE: 'Future Date',
  STALE_DATE: 'Stale Date',
  UNKNOWN_FACILITY: 'Unknown Facility',
  STATISTICAL_OUTLIER: 'Statistical Outlier',
  MISSING_EMISSION_FACTOR: 'Missing Emission Factor',
  DUPLICATE_CANDIDATE: 'Possible Duplicate',
  PERIOD_GAP: 'Billing Period Gap',
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string | number; sub?: string; color?: string
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`mt-1 text-3xl font-semibold ${color || 'text-gray-900'}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-gray-400">{sub}</p>}
    </div>
  )
}

export default function Dashboard() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
    refetchInterval: 30_000,
  })

  if (isLoading) return <div className="py-12 text-center text-gray-500">Loading…</div>
  if (error || !stats) return <div className="py-12 text-center text-red-500">Failed to load dashboard</div>

  const totalCo2t = (stats.total_co2e_kg / 1000).toFixed(2)
  const pendingPct = stats.total_records
    ? Math.round((stats.status_breakdown.pending + stats.status_breakdown.flagged) / stats.total_records * 100)
    : 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Overview</h1>
        <p className="mt-0.5 text-sm text-gray-500">
          Approved records only. Pending review: {stats.status_breakdown.pending + stats.status_breakdown.flagged} records ({pendingPct}%).
        </p>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Records" value={stats.total_records.toLocaleString()} />
        <StatCard
          label="Approved CO₂e"
          value={`${totalCo2t} t`}
          sub="tCO₂e from approved records"
          color="text-green-700"
        />
        <StatCard
          label="Pending Review"
          value={(stats.status_breakdown.pending + stats.status_breakdown.flagged).toLocaleString()}
          sub={`${stats.status_breakdown.flagged} flagged, ${stats.status_breakdown.pending} pending`}
          color="text-amber-600"
        />
        <StatCard
          label="Rejected"
          value={stats.status_breakdown.rejected.toLocaleString()}
          color="text-red-600"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Scope breakdown */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">CO₂e by Scope (Approved)</h2>
          {stats.scope_co2e_kg.length === 0 ? (
            <p className="text-sm text-gray-400">No approved records yet.</p>
          ) : (
            <div className="space-y-3">
              {stats.scope_co2e_kg.map((s) => {
                const tco2 = ((s.co2e_kg || 0) / 1000).toFixed(2)
                const pct = stats.total_co2e_kg > 0
                  ? Math.round((s.co2e_kg || 0) / stats.total_co2e_kg * 100)
                  : 0
                return (
                  <div key={s.scope}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${SCOPE_COLORS[s.scope]}`}>
                        Scope {s.scope}
                      </span>
                      <span className="text-gray-700 font-medium">{tco2} tCO₂e</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-green-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Source breakdown */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Records by Source</h2>
          {stats.source_breakdown.length === 0 ? (
            <p className="text-sm text-gray-400">No records ingested yet. Upload data to begin.</p>
          ) : (
            <div className="space-y-3">
              {stats.source_breakdown.map((s) => (
                <div key={s.source_type} className="flex justify-between items-center text-sm">
                  <span className="text-gray-700">{SOURCE_LABELS[s.source_type] || s.source_type}</span>
                  <div className="text-right">
                    <span className="font-medium text-gray-900">{s.count} records</span>
                    {s.co2e_kg != null && (
                      <span className="ml-2 text-gray-400">
                        ({((s.co2e_kg || 0) / 1000).toFixed(1)} tCO₂e)
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quality flags */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Quality Flags</h2>
          {Object.keys(stats.flag_breakdown).length === 0 ? (
            <p className="text-sm text-gray-400">No quality flags detected.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {Object.entries(stats.flag_breakdown)
                .sort(([, a], [, b]) => b - a)
                .map(([flag, count]) => (
                  <span
                    key={flag}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-50 border border-amber-200 text-xs text-amber-800"
                  >
                    <span className="font-medium">{FLAG_LABELS[flag] || flag}</span>
                    <span className="bg-amber-200 text-amber-900 rounded-full px-1.5 py-0.5 text-xs font-bold">
                      {count}
                    </span>
                  </span>
                ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
