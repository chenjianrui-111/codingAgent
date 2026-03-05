import { useEffect, useState } from 'react'
import type { DatasetDetailResponse, DatasetListItem } from '../api/types'
import { getDatasetDetail, listDatasets, deleteDataset } from '../api/client'

interface Props {
  sessionId: string
  accessToken?: string
  selectedDatasetId: string | null
  onSelectDataset: (datasetId: string) => void
  refreshKey?: number
}

export default function DatasetExplorer({
  sessionId,
  accessToken,
  selectedDatasetId,
  onSelectDataset,
  refreshKey,
}: Props) {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([])
  const [detail, setDetail] = useState<DatasetDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<'schema' | 'data' | 'stats'>('schema')

  // Fetch dataset list
  useEffect(() => {
    listDatasets(sessionId, accessToken)
      .then((r) => setDatasets(r.datasets))
      .catch(() => {})
  }, [sessionId, accessToken, refreshKey])

  // Fetch detail when selected
  useEffect(() => {
    if (!selectedDatasetId) {
      setDetail(null)
      return
    }
    setLoading(true)
    getDatasetDetail(selectedDatasetId, accessToken)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [selectedDatasetId, accessToken])

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Dataset list */}
      {datasets.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {datasets.map((ds) => (
            <button
              key={ds.dataset_id}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                selectedDatasetId === ds.dataset_id
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
              }`}
              onClick={() => onSelectDataset(ds.dataset_id)}
            >
              <span className="mr-1">{ds.file_type === 'csv' ? '\u{1F4CA}' : '\u{1F4C4}'}</span>
              {ds.name}
              <span className="ml-1 text-gray-400">
                ({ds.row_count.toLocaleString()} rows)
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Detail view */}
      {loading && (
        <div className="text-sm text-gray-500 animate-pulse">Loading dataset...</div>
      )}

      {detail && !loading && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2 bg-gray-850 border-b border-gray-800">
            <div>
              <span className="font-medium text-gray-200">{detail.name}</span>
              <span className="ml-2 text-xs text-gray-500">
                {detail.row_count.toLocaleString()} rows / {detail.column_count} cols / {formatBytes(detail.file_size_bytes)}
              </span>
            </div>
            <div className="flex gap-1">
              {(['schema', 'data', 'stats'] as const).map((t) => (
                <button
                  key={t}
                  className={`px-2 py-0.5 text-xs rounded ${
                    tab === t ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'
                  }`}
                  onClick={() => setTab(t)}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Content */}
          <div className="p-3 max-h-64 overflow-auto text-xs">
            {tab === 'schema' && (
              <table className="w-full">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-800">
                    <th className="text-left py-1 pr-4">Column</th>
                    <th className="text-left py-1 pr-4">Type</th>
                    <th className="text-right py-1 pr-4">Unique</th>
                    <th className="text-right py-1 pr-4">Nulls</th>
                    <th className="text-left py-1">Sample</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.columns.map((col) => (
                    <tr key={col.name} className="border-b border-gray-800/50 text-gray-300">
                      <td className="py-1 pr-4 font-mono text-blue-300">{col.name}</td>
                      <td className="py-1 pr-4 text-gray-400">{col.dtype}</td>
                      <td className="py-1 pr-4 text-right">{col.unique_count}</td>
                      <td className="py-1 pr-4 text-right">
                        {col.null_count > 0 ? (
                          <span className="text-yellow-400">{col.null_count}</span>
                        ) : (
                          <span className="text-green-400">0</span>
                        )}
                      </td>
                      <td className="py-1 text-gray-500 truncate max-w-[200px]">
                        {col.sample_values.slice(0, 3).join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {tab === 'data' && detail.sample_rows.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-800">
                      {Object.keys(detail.sample_rows[0]).map((k) => (
                        <th key={k} className="text-left py-1 pr-3 font-mono whitespace-nowrap">
                          {k}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.sample_rows.map((row, i) => (
                      <tr key={i} className="border-b border-gray-800/50 text-gray-300">
                        {Object.values(row).map((v, j) => (
                          <td key={j} className="py-1 pr-3 truncate max-w-[150px]">
                            {v === null ? <span className="text-gray-600">null</span> : String(v)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {tab === 'stats' && detail.summary && (
              <pre className="text-gray-300 whitespace-pre-wrap">
                {JSON.stringify(detail.summary, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
