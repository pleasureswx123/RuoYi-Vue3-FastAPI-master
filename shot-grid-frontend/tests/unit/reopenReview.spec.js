import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ReopenReviewButton from '@/components/review/ReopenReviewButton.vue'
import { useSessionStore } from '@/store/modules/session'
import { getVersionReviewContext, reopenVersionReview } from '@/api/shot-grid/reviews'
vi.mock('@/api/shot-grid/reviews', () => ({ getVersionReviewContext: vi.fn(), reopenVersionReview: vi.fn() }))
let wrapper
const version = { versionId: 42, versionStatus: 'final', versionNumber: 'V002' }
const state = { canReopenReview: true, taskLockVersion: 5, currentVersion: { reviewCycle: 1, lockVersion: 3 } }
const click = async text => { const node = [...document.querySelectorAll('button')].find(node => node.textContent.trim() === text); expect(node).toBeTruthy(); node.click(); await flushPromises() }
beforeEach(() => {
  setActivePinia(createPinia()); vi.clearAllMocks()
  useSessionStore().permissions = ['shotgrid:version:reopen', 'shotgrid:version:review']
  getVersionReviewContext.mockResolvedValue({ data: structuredClone(state) })
  reopenVersionReview.mockResolvedValue({ data: { autoReviewListId: 6, reviewCycle: 2 } })
})
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = '' })
function render() { wrapper = mount(ReopenReviewButton, { props: { version }, attachTo: document.body }); return wrapper }
describe('重新审核表单', () => {
  it('空原因校验失败，填写后提交快照，加载时禁止重复提交', async () => {
    render(); await click('重新审核'); await click('确认重新审核')
    expect(reopenVersionReview).not.toHaveBeenCalled()
    const input = document.querySelector('textarea'); input.value = '发现新问题'; input.dispatchEvent(new Event('input', { bubbles: true })); await flushPromises()
    let resolve; reopenVersionReview.mockImplementation(() => new Promise(done => { resolve = done }))
    await click('确认重新审核'); await click('确认重新审核')
    expect(reopenVersionReview).toHaveBeenCalledTimes(1)
    expect(reopenVersionReview.mock.calls[0][1]).toEqual({ reason: '发现新问题', lockVersion: 3, taskLockVersion: 5, reviewCycle: 1 })
    resolve({ data: { autoReviewListId: 6 } }); await flushPromises()
    expect(wrapper.emitted('reopened')).toHaveLength(1)
  })
  it('异步校验期间连续点击只提交一次，切换版本后不提交旧快照', async () => {
    render(); await click('重新审核')
    let finishValidation
    const validation = vi.spyOn(wrapper.vm.form, 'validate').mockImplementation(() => new Promise(resolve => { finishValidation = resolve }))
    const submit = [...document.querySelectorAll('button')].find(node => node.textContent.trim() === '确认重新审核')
    submit.click(); submit.click(); await flushPromises()
    expect(validation).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ version: { ...version, versionId: 99 } })
    finishValidation(true); await flushPromises()
    expect(reopenVersionReview).not.toHaveBeenCalled()
  })
  it('服务端拒绝时展示原因并禁用确认', async () => {
    getVersionReviewContext.mockResolvedValue({ data: { ...state, canReopenReview: false, reopenBlockedReason: 'NAS 正在执行' } })
    render(); await click('重新审核')
    expect(document.body.textContent).toContain('NAS 正在执行')
    const submit = [...document.querySelectorAll('button')].find(node => node.textContent.trim() === '确认重新审核')
    expect(submit.disabled).toBe(true)
    expect(reopenVersionReview).not.toHaveBeenCalled()
  })
  it('没有独立权限时不显示入口', () => {
    useSessionStore().permissions = ['shotgrid:version:review']; render()
    expect(wrapper.find('button').exists()).toBe(false)
  })
  it('切换版本丢弃迟到上下文', async () => {
    let resolve; getVersionReviewContext.mockImplementation(() => new Promise(done => { resolve = done }))
    render(); await click('重新审核'); await wrapper.setProps({ version: { ...version, versionId: 99 } })
    resolve({ data: state }); await flushPromises()
    expect(reopenVersionReview).not.toHaveBeenCalled()
    expect(wrapper.vm.snapshot).toBeNull()
  })
})
