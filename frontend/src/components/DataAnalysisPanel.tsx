import { useCallback, useRef, useState } from 'react'
import type { DatasetUploadResponse, StreamEvent } from '../api/types'
import { dataAnalyzeStream, autoEDAStream } from '../api/client'
import DataUploadPanel from './DataUploadPanel'
import DatasetExplorer from './DatasetExplorer'
import CodeCell from './CodeCell'
import ChartViewer from './ChartViewer'

interface Props {
  sessionId: string
  accessToken?: string
  onBack: () => void
}

interface AnalysisMessage {
  id: string
  type: 'user' | 'assistant' | 'code' | 'chart' | 'status' | 'error'
  content: string
  code?: string
  figures?: Array<{ data_base64?: string; url?: string; format: string }>
}

export default function DataAnalysisPanel({ sessionId, accessToken, onBack }: Props) {
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AnalysisMessage[]>([])
  const [query, setQuery] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }), 50)
  }

  const addMessage = (msg: Omit<AnalysisMessage, 'id'>) => {
    setMessages((prev) => [...prev, { ...msg, id: `dam_${Date.now()}_${Math.random()}` }])
    scrollToBottom()
  }

  const appendToLast = (text: string) => {
    setMessages((prev) => {
      const msgs = [...prev]
      if (msgs.length > 0 && msgs[msgs.length - 1].type === 'assistant') {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: msgs[msgs.length - 1].content + text }
      } else {
        msgs.push({ id: `dam_${Date.now()}`, type: 'assistant', content: text })
      }
      return msgs
    })
    scrollToBottom()
  }

  const handleUploaded = useCallback((ds: DatasetUploadResponse) => {
    setSelectedDatasetId(ds.dataset_id)
    setRefreshKey((k) => k + 1)
    addMessage({
      type: 'status',
      content: `Dataset "${ds.name}" uploaded: ${ds.row_count.toLocaleString()} rows, ${ds.column_count} columns (${ds.file_type})`,
    })
  }, [])

  const processSSE = async (response: Response) => {
    const reader = response.body?.getReader()
    if (!reader) return

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event: StreamEvent = JSON.parse(line.slice(6))
          switch (event.type) {
            case 'text_delta':
              appendToLast(event.data.text as string)
              break
            case 'tool_call':
              addMessage({
                type: 'code',
                content: `Using tool: ${event.data.tool}`,
                code: typeof event.data.input === 'object'
                  ? (event.data.input as Record<string, unknown>).code as string || JSON.stringify(event.data.input, null, 2)
                  : String(event.data.input),
              })
              break
            case 'tool_result': {
              const output = event.data.output as string
              if (output) addMessage({ type: 'assistant', content: output })
              break
            }
            case 'eda_code':
              addMessage({
                type: 'code',
                content: `Step: ${event.data.step}`,
                code: event.data.code as string,
              })
              break
            case 'eda_result': {
              const edaData = event.data as Record<string, unknown>
              const parts: string[] = []
              if (edaData.stdout) parts.push(edaData.stdout as string)
              if (edaData.display) parts.push(edaData.display as string)
              if (parts.length > 0) {
                addMessage({ type: 'assistant', content: parts.join('\n') })
              }
              if (edaData.figures && (edaData.figures as unknown[]).length > 0) {
                addMessage({
                  type: 'chart',
                  content: '',
                  figures: edaData.figures as Array<{ data_base64: string; format: string }>,
                })
              }
              break
            }
            case 'figures': {
              const figData = event.data as Record<string, unknown>
              const figs = figData.figures as Array<{ data_base64?: string; url?: string; format: string }>
              if (figs && figs.length > 0) {
                addMessage({ type: 'chart', content: '', figures: figs })
              }
              break
            }
            case 'status':
              addMessage({ type: 'status', content: event.data.message as string })
              break
            case 'error':
              addMessage({ type: 'error', content: event.data.message as string })
              break
            case 'done':
              break
          }
        } catch {
          // skip malformed events
        }
      }
    }
  }

  const handleSubmit = async () => {
    if (!query.trim() || !selectedDatasetId || streaming) return

    const q = query.trim()
    setQuery('')
    addMessage({ type: 'user', content: q })
    setStreaming(true)

    try {
      const res = await dataAnalyzeStream(sessionId, selectedDatasetId, q, accessToken)
      await processSSE(res)
    } catch (e: any) {
      addMessage({ type: 'error', content: e.message || 'Analysis failed' })
    } finally {
      setStreaming(false)
    }
  }

  const handleAutoEDA = async () => {
    if (!selectedDatasetId || streaming) return

    addMessage({ type: 'user', content: 'Run automated Exploratory Data Analysis' })
    setStreaming(true)

    try {
      const res = await autoEDAStream(sessionId, selectedDatasetId, accessToken)
      await processSSE(res)
    } catch (e: any) {
      addMessage({ type: 'error', content: e.message || 'Auto EDA failed' })
    } finally {
      setStreaming(false)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-200">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center gap-3">
          <button
            className="text-gray-400 hover:text-gray-200 text-sm"
            onClick={onBack}
          >
            &larr; Back to Chat
          </button>
          <h1 className="text-lg font-semibold text-gray-100">Data Analysis Agent</h1>
        </div>
        {selectedDatasetId && (
          <button
            className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-medium disabled:opacity-50"
            onClick={handleAutoEDA}
            disabled={streaming}
          >
            Auto EDA
          </button>
        )}
      </header>

      {/* Dataset panel */}
      <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/50">
        <DataUploadPanel
          sessionId={sessionId}
          accessToken={accessToken}
          onUploaded={handleUploaded}
        />
        <div className="mt-3">
          <DatasetExplorer
            sessionId={sessionId}
            accessToken={accessToken}
            selectedDatasetId={selectedDatasetId}
            onSelectDataset={setSelectedDatasetId}
            refreshKey={refreshKey}
          />
        </div>
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-20">
            <p className="text-lg">Upload a dataset and start asking questions</p>
            <p className="text-sm mt-2">
              Try: "Show me the distribution of sales by region" or "What are the top correlations?"
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id}>
            {msg.type === 'user' && (
              <div className="flex justify-end">
                <div className="bg-blue-600 text-white px-4 py-2 rounded-2xl rounded-br-md max-w-[80%] text-sm">
                  {msg.content}
                </div>
              </div>
            )}

            {msg.type === 'assistant' && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-sm">
                <pre className="whitespace-pre-wrap font-mono text-gray-300">{msg.content}</pre>
              </div>
            )}

            {msg.type === 'code' && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                <div className="px-3 py-1 text-xs text-gray-500 bg-gray-850 border-b border-gray-800">
                  {msg.content}
                </div>
                {msg.code && (
                  <pre className="p-3 text-xs font-mono text-green-300 overflow-x-auto">
                    {msg.code}
                  </pre>
                )}
              </div>
            )}

            {msg.type === 'chart' && msg.figures && (
              <ChartViewer figures={msg.figures} />
            )}

            {msg.type === 'status' && (
              <div className="text-xs text-gray-500 text-center py-1">{msg.content}</div>
            )}

            {msg.type === 'error' && (
              <div className="bg-red-950/30 border border-red-900/50 rounded-lg px-4 py-2 text-sm text-red-400">
                {msg.content}
              </div>
            )}
          </div>
        ))}

        {streaming && (
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            Analyzing...
          </div>
        )}
      </div>

      {/* Code cell */}
      {selectedDatasetId && (
        <div className="px-4 py-2 border-t border-gray-800 bg-gray-900/50">
          <CodeCell
            sessionId={sessionId}
            accessToken={accessToken}
            datasetId={selectedDatasetId}
          />
        </div>
      )}

      {/* Input bar */}
      <div className="px-4 py-3 border-t border-gray-800 bg-gray-900">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit()
              }
            }}
            placeholder={
              selectedDatasetId
                ? 'Ask a question about your data...'
                : 'Upload a dataset first'
            }
            disabled={!selectedDatasetId || streaming}
            className="flex-1 bg-gray-800 text-gray-200 rounded-lg px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500 disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={!query.trim() || !selectedDatasetId || streaming}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Analyze
          </button>
        </div>
      </div>
    </div>
  )
}
