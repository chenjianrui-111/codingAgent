import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { ChatMessage } from '../api/types'

interface Props {
  message: ChatMessage
}

export default function MessageBubble({ message }: Props) {
  if (message.type === 'user') {
    return (
      <div className="flex justify-end px-4 py-2">
        <div className="max-w-[80%] px-4 py-2 rounded-2xl bg-blue-600 text-white text-sm">
          {message.content}
        </div>
      </div>
    )
  }

  if (message.type === 'assistant') {
    return (
      <div className="px-4 py-2">
        <div className="max-w-[90%] text-sm text-gray-200 prose prose-invert prose-sm max-w-none">
          <ReactMarkdown
            components={{
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '')
                const inline = !match
                return inline ? (
                  <code className="bg-gray-800 px-1 rounded text-blue-300" {...props}>
                    {children}
                  </code>
                ) : (
                  <SyntaxHighlighter
                    style={vscDarkPlus}
                    language={match[1]}
                    PreTag="div"
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                )
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    )
  }

  // Status messages
  return (
    <div className="px-4 py-1 text-xs text-gray-500 italic">
      {message.content}
    </div>
  )
}
