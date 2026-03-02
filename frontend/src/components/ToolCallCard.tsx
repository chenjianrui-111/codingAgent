import { useState } from 'react'
import type { ChatMessage } from '../api/types'

interface Props {
  message: ChatMessage
}

export default function ToolCallCard({ message }: Props) {
  const [expanded, setExpanded] = useState(false)
  const isResult = message.type === 'tool_result'

  return (
    <div className="mx-4 my-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-mono w-full text-left ${
          isResult
            ? message.success
              ? 'bg-green-950/50 text-green-300 border border-green-800/50'
              : 'bg-red-950/50 text-red-300 border border-red-800/50'
            : 'bg-gray-800/50 text-gray-300 border border-gray-700/50'
        }`}
      >
        <span className="text-xs">{expanded ? '▼' : '▶'}</span>
        <span className="font-semibold">{message.toolName || 'tool'}</span>
        {isResult && (
          <span className={`ml-auto text-xs ${message.success ? 'text-green-500' : 'text-red-500'}`}>
            {message.success ? 'OK' : 'FAIL'}
          </span>
        )}
      </button>
      {expanded && (
        <pre className="mt-1 p-3 bg-gray-900 rounded-lg text-xs overflow-x-auto max-h-64 overflow-y-auto text-gray-300 border border-gray-800">
          {isResult
            ? message.content
            : JSON.stringify(message.toolInput, null, 2)}
        </pre>
      )}
    </div>
  )
}
