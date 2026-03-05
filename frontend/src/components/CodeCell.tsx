import { useState } from 'react'
import { executeCode } from '../api/client'
import type { DataExecuteResponse } from '../api/types'
import ChartViewer from './ChartViewer'

interface Props {
  sessionId: string
  accessToken?: string
  datasetId?: string
  initialCode?: string
}

export default function CodeCell({ sessionId, accessToken, datasetId, initialCode }: Props) {
  const [code, setCode] = useState(initialCode || '')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<DataExecuteResponse | null>(null)

  const handleRun = async () => {
    if (!code.trim() || running) return
    setRunning(true)
    setResult(null)
    try {
      const res = await executeCode(sessionId, code, datasetId, accessToken)
      setResult(res)
    } catch (e: any) {
      setResult({
        success: false,
        stdout: '',
        stderr: e.message || 'Execution failed',
        display: null,
        figures: [],
        execution_time_ms: 0,
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="rounded-lg border border-gray-800 overflow-hidden bg-gray-900">
      {/* Code input */}
      <div className="relative">
        <div className="flex items-center justify-between px-3 py-1.5 bg-gray-850 border-b border-gray-800">
          <span className="text-xs text-gray-500 font-mono">Python</span>
          <div className="flex items-center gap-2">
            {result && (
              <span className="text-xs text-gray-500">{result.execution_time_ms}ms</span>
            )}
            <button
              className={`px-2 py-0.5 text-xs rounded font-medium ${
                running
                  ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                  : 'bg-green-600 hover:bg-green-500 text-white'
              }`}
              onClick={handleRun}
              disabled={running}
            >
              {running ? 'Running...' : 'Run'}
            </button>
          </div>
        </div>
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="w-full bg-gray-950 text-gray-200 font-mono text-sm p-3 resize-y min-h-[80px] outline-none"
          placeholder="# Write Python code here..."
          spellCheck={false}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              handleRun()
            }
          }}
        />
      </div>

      {/* Output */}
      {result && (
        <div className="border-t border-gray-800">
          {/* Text output */}
          {(result.stdout || result.display) && (
            <div className="p-3 bg-gray-950">
              {result.stdout && (
                <pre className="text-sm text-gray-300 font-mono whitespace-pre-wrap">
                  {result.stdout}
                </pre>
              )}
              {result.display && (
                <pre className="text-sm text-blue-300 font-mono whitespace-pre-wrap mt-1">
                  {result.display}
                </pre>
              )}
            </div>
          )}

          {/* Error output */}
          {result.stderr && !result.success && (
            <div className="p-3 bg-red-950/30">
              <pre className="text-sm text-red-400 font-mono whitespace-pre-wrap">
                {result.stderr}
              </pre>
            </div>
          )}

          {/* Charts */}
          {result.figures.length > 0 && (
            <div className="p-3">
              <ChartViewer figures={result.figures} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
