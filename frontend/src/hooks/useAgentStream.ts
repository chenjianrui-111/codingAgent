import { useCallback } from 'react'
import { agentStream } from '../api/client'
import { useChatStore } from '../stores/chatStore'
import type { StreamEvent } from '../api/types'

export function useAgentStream() {
  const sessionId = useChatStore((s) => s.sessionId)
  const accessToken = useChatStore((s) => s.accessToken)
  const addMessage = useChatStore((s) => s.addMessage)
  const appendToLastAssistant = useChatStore((s) => s.appendToLastAssistant)
  const setStreaming = useChatStore((s) => s.setStreaming)
  const setStatus = useChatStore((s) => s.setStatus)

  const sendMessage = useCallback(
    async (query: string, currentFile?: string, workspace?: string) => {
      if (!sessionId) return

      addMessage({ type: 'user', content: query })
      setStreaming(true)
      setStatus('Connecting...')

      try {
        const response = await agentStream(sessionId, query, currentFile, workspace, accessToken || undefined)
        const reader = response.body!.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n\n')
          buffer = lines.pop()!

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const event: StreamEvent = JSON.parse(line.slice(6))
              handleEvent(event)
            } catch {
              // skip malformed events
            }
          }
        }
      } catch (err) {
        addMessage({
          type: 'status',
          content: `Error: ${err instanceof Error ? err.message : String(err)}`,
        })
      } finally {
        setStreaming(false)
        setStatus(null)
      }
    },
    [sessionId, accessToken, addMessage, appendToLastAssistant, setStreaming, setStatus],
  )

  function handleEvent(event: StreamEvent) {
    switch (event.type) {
      case 'status':
        setStatus(event.data.message as string)
        break

      case 'text_delta':
        appendToLastAssistant(event.data.text as string)
        break

      case 'tool_call':
        addMessage({
          type: 'tool_call',
          content: `Calling \`${event.data.tool}\``,
          toolName: event.data.tool as string,
          toolInput: event.data.input as Record<string, unknown>,
          toolId: event.data.id as string,
        })
        setStatus(`Running ${event.data.tool}...`)
        break

      case 'tool_result':
        addMessage({
          type: 'tool_result',
          content: (event.data.output as string) || '',
          toolName: event.data.tool as string,
          toolId: event.data.id as string,
          success: event.data.success as boolean,
        })
        break

      case 'diff_preview':
        addMessage({
          type: 'diff_preview',
          content: (event.data.detail as string) || '',
          filePath: event.data.path as string,
        })
        break

      case 'approval_required':
        addMessage({
          type: 'approval',
          content: (event.data.reason as string) || 'Approval required',
          runId: event.data.run_id as string,
          reason: event.data.reason as string,
        })
        break

      case 'error':
        addMessage({
          type: 'status',
          content: `Error: ${event.data.message}`,
        })
        break

      case 'done':
        setStatus(null)
        break
    }
  }

  return { sendMessage }
}
