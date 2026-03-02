import type { ChatMessage } from '../api/types'

interface Props {
  message: ChatMessage
}

export default function ApprovalDialog({ message }: Props) {
  return (
    <div className="mx-4 my-2 border border-orange-700/50 rounded-lg p-4 bg-orange-950/20">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-orange-400 text-lg">&#9888;</span>
        <span className="text-sm font-semibold text-orange-300">Approval Required</span>
      </div>
      <p className="text-sm text-gray-300 mb-3">{message.reason || message.content}</p>
      <div className="flex gap-2">
        <button className="px-3 py-1 rounded bg-green-700 hover:bg-green-600 text-sm text-white">
          Approve
        </button>
        <button className="px-3 py-1 rounded bg-red-700 hover:bg-red-600 text-sm text-white">
          Reject
        </button>
      </div>
    </div>
  )
}
