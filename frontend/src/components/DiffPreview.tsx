import type { ChatMessage } from '../api/types'

interface Props {
  message: ChatMessage
}

export default function DiffPreview({ message }: Props) {
  return (
    <div className="mx-4 my-2 border border-yellow-800/50 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-yellow-950/30">
        <span className="text-sm font-mono text-yellow-300">
          {message.filePath || 'file changed'}
        </span>
      </div>
      <pre className="p-3 bg-gray-900 text-xs overflow-x-auto max-h-48 overflow-y-auto text-gray-300">
        {message.content}
      </pre>
    </div>
  )
}
