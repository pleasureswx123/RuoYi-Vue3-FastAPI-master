import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import request from '@/utils/request'
import { useRealtimeStore } from '@/store/modules/realtime'

vi.mock('@/utils/request', () => ({ default: vi.fn() }))
vi.mock('@/utils/auth', () => ({ getToken: () => 'session' }))
class Socket {
  static instances = []
  constructor(url) { this.url = url; this.readyState = 0; this.sent = []; Socket.instances.push(this) }
  send(raw) { this.sent.push(JSON.parse(raw)) }
  close() { this.readyState = 3; this.onclose?.() }
  open() { this.readyState = 1; this.onopen() }
  receive(message) { this.onmessage({ data: JSON.stringify(message) }) }
}
const settle = async () => { await Promise.resolve(); await Promise.resolve() }
describe('统一 WebSocket', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    Socket.instances = []
    vi.stubGlobal('WebSocket', Socket)
    request.mockResolvedValue({ data: { ticket: 'one-time' } })
  })
  afterEach(() => { useRealtimeStore().reset(); vi.useRealTimers(); vi.unstubAllGlobals() })
  it('共享连接、首帧票据认证、订阅与退出清理', async () => {
    const store = useRealtimeStore()
    const one = vi.fn(); const two = vi.fn()
    const off = store.subscribe('shot-grid.version', 29, one)
    const off2 = store.subscribe('shot-grid.version', 29, two)
    await settle()
    expect(Socket.instances).toHaveLength(1)
    const ws = Socket.instances[0]
    expect(ws.url).not.toContain('session')
    expect(ws.url).not.toContain('one-time')
    ws.open(); expect(ws.sent[0]).toEqual({ type: 'auth', ticket: 'one-time' })
    ws.receive({ type: 'ready' })
    expect(ws.sent.filter(item => item.type === 'subscribe')).toHaveLength(1)
    ws.receive({ type: 'event', topic: 'shot-grid.version', resourceId: 29 })
    expect(one).toHaveBeenCalledTimes(1); expect(two).toHaveBeenCalledTimes(1)
    off(); expect(ws.readyState).toBe(1)
    off2(); expect(ws.readyState).toBe(3)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('重连恢复订阅，登出丢弃迟到票据', async () => {
    const store = useRealtimeStore()
    store.subscribe('shot-grid.version', 29, vi.fn())
    await settle()
    Socket.instances[0].open(); Socket.instances[0].receive({ type: 'ready' }); Socket.instances[0].close()
    await vi.advanceTimersByTimeAsync(2000)
    expect(Socket.instances).toHaveLength(2)
    Socket.instances[1].open(); Socket.instances[1].receive({ type: 'ready' })
    expect(Socket.instances[1].sent).toContainEqual({ type: 'subscribe', topic: 'shot-grid.version', resourceId: 29 })
    store.reset()
    let finish
    request.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    store.subscribe('shot-grid.version', 30, vi.fn())
    store.reset()
    finish({ data: { ticket: 'stale' } }); await settle()
    expect(Socket.instances).toHaveLength(2)
  })
})
