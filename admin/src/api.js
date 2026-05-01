const BASE = ''

export async function get(path) {
  const r = await fetch(`${BASE}${path}`)
  return r.json()
}

export async function post(path, data) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return r.json()
}

export async function del(path) {
  const r = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  return r.json()
}

export async function put(path, data) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
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
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        while (buffer.includes('\n\n')) {
          const [event, rest] = buffer.split('\n\n', 1)
          buffer = rest

          let eventType = '', dataStr = ''
          for (const line of event.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7)
            else if (line.startsWith('data: ')) dataStr = line.slice(6)
          }
          if (eventType && dataStr) {
            onEvent(eventType, JSON.parse(dataStr))
          } else if (dataStr) {
            onToken(JSON.parse(dataStr))
          }
        }
      }
      resolve()
    } catch (e) {
      reject(e)
    }
  })
}
