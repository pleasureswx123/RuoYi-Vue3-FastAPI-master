import { ref } from 'vue'
import { defineStore } from 'pinia'
import request from '@/utils/request'
import { getToken } from '@/utils/auth'

export function realtimeUrl() {
  const base = new URL(import.meta.env.VITE_APP_BASE_API || '/dev-api', window.location.origin)
  base.pathname = `${base.pathname.replace(/\/$/, '')}/realtime/ws`
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  return base.href
}

// 每个应用实例共用一条连接；页面只持有订阅，不自行建立 Socket。
export const useRealtimeStore = defineStore('realtime', () => {
  const status = ref('idle')
  const listeners = new Map()
  let socket = null
  let reconnectTimer = null
  let heartbeat = null
  let attempt = 0
  let generation = 0
  let lastPong = 0

  function send(message) {
    if (socket?.readyState === 1) socket.send(JSON.stringify(message))
  }
  function notify(key, message) {
    for (const listener of listeners.get(key) || []) listener(message)
  }
  function scheduleReconnect() {
    if (!listeners.size || !getToken() || reconnectTimer) return
    status.value = 'reconnecting'
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, Math.min(30000, 1000 * 2 ** Math.min(attempt++, 5)) + Math.random() * 500)
  }
  async function connect() {
    if (socket || !listeners.size || !getToken() || status.value === 'connecting') return
    const current = ++generation
    status.value = 'connecting'
    try {
      const response = await request({ url: '/realtime/ticket', method: 'post', headers: { repeatSubmit: false }, silentError: true })
      if (current !== generation || !listeners.size) return
      const ws = new WebSocket(realtimeUrl())
      socket = ws
      const authTimer = setTimeout(() => ws.close(), 10000)
      ws.onopen = () => {
        if (current !== generation) return ws.close()
        ws.send(JSON.stringify({ type: 'auth', ticket: response.data.ticket }))
      }
      ws.onmessage = event => {
        if (current !== generation) return
        let message
        try { message = JSON.parse(event.data) } catch { return }
        if (message.type === 'ready') {
          clearTimeout(authTimer)
          status.value = 'connected'
          lastPong = Date.now()
          for (const key of listeners.keys()) {
            const [topic, resourceId] = key.split(':')
            send({ type: 'subscribe', topic, resourceId: Number(resourceId) })
          }
          heartbeat = setInterval(() => {
            if (Date.now() - lastPong > 60000) return ws.close()
            send({ type: 'ping' })
          }, 20000)
        } else if (message.type === 'pong') {
          lastPong = Date.now()
        } else if (['event', 'subscribed'].includes(message.type)) {
          if (message.type === 'subscribed') attempt = 0
          notify(`${message.topic}:${message.resourceId}`, message)
        }
      }
      ws.onerror = () => ws.close()
      ws.onclose = () => {
        clearTimeout(authTimer)
        if (current !== generation) return
        clearInterval(heartbeat)
        heartbeat = null
        socket = null
        status.value = 'disconnected'
        scheduleReconnect()
      }
    } catch {
      if (current !== generation) return
      status.value = 'disconnected'
      scheduleReconnect()
    }
  }
  function stop() {
    generation += 1
    clearTimeout(reconnectTimer)
    clearInterval(heartbeat)
    reconnectTimer = null
    heartbeat = null
    socket?.close()
    socket = null
    status.value = 'idle'
  }
  function reset() {
    stop()
    listeners.clear()
    attempt = 0
  }
  function subscribe(topic, resourceId, listener) {
    if (topic !== 'shot-grid.version' || !Number.isSafeInteger(resourceId) || resourceId < 1) throw new Error('无效实时订阅')
    const key = `${topic}:${resourceId}`
    if (!listeners.has(key)) {
      listeners.set(key, new Set())
      if (status.value === 'connected') send({ type: 'subscribe', topic, resourceId })
    }
    listeners.get(key).add(listener)
    if (status.value !== 'connected') connect()
    return () => {
      listeners.get(key)?.delete(listener)
      if (listeners.get(key)?.size === 0) {
        listeners.delete(key)
        send({ type: 'unsubscribe', topic, resourceId })
      }
      if (!listeners.size) stop()
    }
  }
  return { status, subscribe, reset }
})
