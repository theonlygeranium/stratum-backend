# STRATUM Frontend Integration Patch

The attached frontend contract clarifies that the live Phase 1 component still calls `mockStreamResponse()` directly. Setting `VITE_STRATUM_API_URL` alone will not connect the backend until the React source adds a fetch/SSE adapter.

When the frontend repo is available, apply this minimal patch:

1. Copy `stratumApi.ts` into `src/stratum/stratumApi.ts`.
2. In `src/stratum/StratumChat.tsx`, import `streamFromBackend` from `./stratumApi`.
3. Also import `STRATUM_SESSION_KEY` from `./stratumConfig`.
4. Add a stable `sessionId` state backed by `sessionStorage`.
5. In `handleSubmit`, build `nextMessages = [...messages, userMessage]` before `setMessages(nextMessages)`.
6. Replace each `mockStreamResponse(...)` call with a conditional:

```typescript
const stream = STRATUM_BACKEND_ENABLED
  ? streamFromBackend(nextMessages, mode, intakeIndex, intakeAnswers, sessionId)
  : mockStreamResponse(text, mode, intakeAnswers, false)
```

For the intake-complete branch, call:

```typescript
const stream = STRATUM_BACKEND_ENABLED
  ? streamFromBackend(nextMessages, 'intake', nextIndex, newAnswers, sessionId)
  : mockStreamResponse(text, 'intake', newAnswers, true)
```

For escalation mode, call:

```typescript
const stream = STRATUM_BACKEND_ENABLED
  ? streamFromBackend(nextMessages, 'escalation', intakeIndex, intakeAnswers, sessionId)
  : mockStreamResponse(text, 'escalation', intakeAnswers, false)
```

Keep the existing mock path as the fallback when `VITE_STRATUM_API_URL` is unset.

