import { STRATUM_API_URL } from './stratumConfig'
import type {
  ChatMessage,
  ConversationMode,
  StreamEvent,
} from './stratumTypes'

interface ChatPayload {
  messages: ChatMessage[]
  mode: ConversationMode
  intakeIndex: number | null
  intakeAnswers: Record<string, string>
  sessionId: string
}

function apiBaseUrl(): string | null {
  if (!STRATUM_API_URL) return null
  return STRATUM_API_URL.replace(/\/$/, '')
}

function parseSseBlock(block: string): StreamEvent | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')

  if (!data || data === '[DONE]') return null
  return JSON.parse(data) as StreamEvent
}

export async function* streamFromBackend(
  messages: ChatMessage[],
  mode: ConversationMode,
  intakeIndex: number | null,
  intakeAnswers: Record<string, string>,
  sessionId: string,
): AsyncGenerator<StreamEvent> {
  const baseUrl = apiBaseUrl()
  if (!baseUrl) {
    yield { type: 'error', message: 'STRATUM backend URL is not configured.' }
    return
  }

  const payload: ChatPayload = {
    messages,
    mode,
    intakeIndex,
    intakeAnswers,
    sessionId,
  }

  try {
    const response = await fetch(`${baseUrl}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (!response.ok || !response.body) {
      yield { type: 'error', message: 'STRATUM backend returned an unavailable response.' }
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })

      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''

      for (const block of blocks) {
        const event = parseSseBlock(block)
        if (event) yield event
      }

      if (done) break
    }

    if (buffer.trim()) {
      const event = parseSseBlock(buffer)
      if (event) yield event
    }
  } catch {
    yield { type: 'error', message: 'STRATUM could not reach the backend.' }
  }
}

