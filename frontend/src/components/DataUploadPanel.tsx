import { useCallback, useRef, useState } from 'react'
import type { DatasetUploadResponse } from '../api/types'
import { uploadDataset } from '../api/client'

interface Props {
  sessionId: string
  accessToken?: string
  onUploaded: (dataset: DatasetUploadResponse) => void
}

export default function DataUploadPanel({ sessionId, accessToken, onUploaded }: Props) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    async (file: File) => {
      setError(null)
      setUploading(true)
      try {
        const result = await uploadDataset(file, sessionId, accessToken)
        onUploaded(result)
      } catch (e: any) {
        setError(e.message || 'Upload failed')
      } finally {
        setUploading(false)
      }
    },
    [sessionId, accessToken, onUploaded],
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
        dragging
          ? 'border-blue-500 bg-blue-950/30'
          : 'border-gray-700 hover:border-gray-500 bg-gray-900/50'
      }`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        accept=".csv,.xlsx,.xls,.json,.jsonl,.parquet,.tsv"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) handleFile(f)
        }}
      />

      {uploading ? (
        <div className="flex flex-col items-center gap-2">
          <div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-gray-400">Uploading & analyzing...</span>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <svg className="w-10 h-10 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <p className="text-sm text-gray-400">
            Drag & drop a data file or{' '}
            <button
              className="text-blue-400 hover:text-blue-300 underline"
              onClick={() => fileRef.current?.click()}
            >
              browse
            </button>
          </p>
          <p className="text-xs text-gray-600">CSV, Excel, JSON, Parquet (max 200MB)</p>
        </div>
      )}

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  )
}
