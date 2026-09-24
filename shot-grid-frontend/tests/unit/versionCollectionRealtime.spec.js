import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { useVersionCollectionRealtime } from '@/composables/useVersionCollectionRealtime'

const subscribe = vi.hoisted(() => vi.fn())
vi.mock('@/store/modules/realtime', () => ({ useRealtimeStore: () => ({ subscribe }) }))
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

it('旧版本收到新轮次提示后回源并订阅新版本', async () => {
  vi.useFakeTimers()
  const handlers = new Map()
  const stopOld = vi.fn()
  subscribe.mockImplementation((_topic, id, callback) => {
    handlers.set(id, callback)
    return id === 31 ? stopOld : vi.fn()
  })
  const ids = ref([31])
  const refresh = vi.fn(async () => { ids.value = [32] })
  const wrapper = mount({ setup() { useVersionCollectionRealtime(ids, refresh); return {} }, template: '<div />' })
  handlers.get(31)({ reason: 'version.superseded' })
  await vi.advanceTimersByTimeAsync(150)
  await flushPromises()
  expect(refresh).toHaveBeenCalledOnce()
  expect(stopOld).toHaveBeenCalledOnce()
  expect(subscribe).toHaveBeenLastCalledWith('shot-grid.version', 32, expect.any(Function))
  handlers.get(32)({ reason: 'review.reject' })
  await vi.advanceTimersByTimeAsync(150)
  expect(refresh).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

it('合并当前页事件，切页取消旧订阅，卸载清理订阅', async () => {
  vi.useFakeTimers()
  const handlers = new Map()
  const stops = new Map()
  subscribe.mockImplementation((_topic, id, callback) => {
    handlers.set(id, callback)
    const stop = vi.fn()
    stops.set(id, stop)
    return stop
  })
  const ids = ref([31, 32, 31])
  const refresh = vi.fn().mockResolvedValue(undefined)
  const wrapper = mount({ setup() { useVersionCollectionRealtime(ids, refresh); return {} }, template: '<div />' })
  expect(subscribe).toHaveBeenCalledTimes(2)
  handlers.get(31)()
  handlers.get(32)()
  await vi.advanceTimersByTimeAsync(150)
  expect(refresh).toHaveBeenCalledTimes(1)
  ids.value = [32, 33]
  await flushPromises()
  expect(stops.get(31)).toHaveBeenCalledOnce()
  expect(subscribe).toHaveBeenCalledTimes(3)
  wrapper.unmount()
  expect(stops.get(32)).toHaveBeenCalledOnce()
  expect(stops.get(33)).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(30000)
  expect(refresh).toHaveBeenCalledTimes(1)
})
