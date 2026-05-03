const BASE = ''

export async function get(path) {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
  return r.json()
}

export async function post(path, data) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
  return r.json()
}

export async function del(path) {
  const r = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
  return r.json()
}

export async function put(path, data) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
  return r.json()
}

export function streamSSE(path, data, onToken, onEvent) {
  return new Promise(async (resolve, reject) => {
    try {
      const r = await fetch(`${BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })

      if (!r.ok) {
        const text = await r.text()
        reject(new Error(`HTTP ${r.status}: ${text}`))
        return
      }

      if (!r.body) {
        reject(new Error('Response body is empty'))
        return
      }

      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        buffer = buffer + chunk

        while (buffer && buffer.includes('\n\n')) {
          const idx = buffer.indexOf('\n\n')
          const event = buffer.substring(0, idx)
          buffer = buffer.substring(idx + 2)

          let eventType = '', dataStr = ''
          for (const line of event.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7)
            else if (line.startsWith('data: ')) dataStr = line.slice(6)
          }
          if (eventType && dataStr) {
            try {
              onEvent(eventType, JSON.parse(dataStr))
            } catch (e) {
              console.warn('Failed to parse SSE event:', dataStr, e)
            }
          } else if (dataStr) {
            try {
              onToken(JSON.parse(dataStr))
            } catch (e) {
              console.warn('Failed to parse SSE token:', dataStr, e)
            }
          }
        }
      }
      resolve()
    } catch (e) {
      reject(e)
    }
  })
}
