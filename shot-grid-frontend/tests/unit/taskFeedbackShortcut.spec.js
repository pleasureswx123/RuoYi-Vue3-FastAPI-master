import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import TaskFeedbackShortcut from '@/views/task/components/TaskFeedbackShortcut.vue'
import { getTaskIssues } from '@/api/shot-grid/reviews'
vi.mock('@/api/shot-grid/reviews', () => ({ getTaskIssues: vi.fn() }))
const render = props => mount(TaskFeedbackShortcut, { props: { taskId: 15, enabled: true, ...props } })
beforeEach(() => getTaskIssues.mockReset())
it('只统计未关闭问题，点击打开反馈，无权限不请求', async () => {
  getTaskIssues.mockResolvedValue({ data: [{ issueId: 1, status: 'open' }, { issueId: 2, status: 'open' }, { issueId: 3, status: 'closed' }] })
  const wrapper = render()
  await flushPromises()
  expect(wrapper.text()).toBe('待处理反馈 2 条')
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('open')).toHaveLength(1)
  await wrapper.setProps({ enabled: false })
  expect(wrapper.text()).toBe('')
  expect(getTaskIssues).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
it('读取失败可重试，不能显示成零反馈', async () => {
  getTaskIssues.mockRejectedValueOnce(new Error('断网'))
  const wrapper = render()
  await flushPromises()
  expect(wrapper.text()).toContain('加载失败')
  getTaskIssues.mockResolvedValueOnce({ data: [{ issueId: 8, status: 'open' }] })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toBe('待处理反馈 1 条')
  wrapper.unmount()
})
it('刷新取消旧请求并隔离迟到响应', async () => {
  let resolveOld
  getTaskIssues.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
  const wrapper = render()
  const signal = getTaskIssues.mock.calls[0][2].signal
  getTaskIssues.mockResolvedValueOnce({ data: [] })
  await wrapper.setProps({ taskId: 16, refreshKey: 1 })
  await flushPromises()
  resolveOld({ data: [{ issueId: 1, status: 'open' }] })
  await flushPromises()
  expect(signal.aborted).toBe(true)
  expect(wrapper.text()).toBe('')
  wrapper.unmount()
})
