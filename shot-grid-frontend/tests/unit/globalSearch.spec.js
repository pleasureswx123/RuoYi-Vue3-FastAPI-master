import { ElAlert, ElButton, ElEmpty, ElIcon, ElInput, ElScrollbar, ElSkeleton, ElTag } from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { searchShotGrid } from '@/api/shot-grid/search'
import GlobalSearchDialog from '@/components/search/GlobalSearchDialog.vue'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/shot-grid/search', () => ({ searchShotGrid: vi.fn() }))

function mountDialog(permissions = [
  'shotgrid:shot:list',
  'shotgrid:shot:query',
  'shotgrid:asset:list',
  'shotgrid:asset:query',
  'shotgrid:storage:path',
  'shotgrid:version:query'
]) {
  return mount(GlobalSearchDialog, {
    props: { modelValue: true, permissions },
    attachTo: document.body,
    global: {
      components: { ElAlert, ElButton, ElEmpty, ElIcon, ElInput, ElScrollbar, ElSkeleton, ElTag },
      stubs: {
        ElDialog: {
          template: '<div class="dialog-stub"><slot /></div>'
        }
      }
    }
  })
}

describe('全局搜索弹窗', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    push.mockReset()
    searchShotGrid.mockReset()
    searchShotGrid.mockResolvedValue({
      data: {
        shots: {
          items: [{
            resultType: 'shot',
            resultId: '31',
            projectCode: 'LCFR',
            projectName: '罗刹夫人',
            title: 'EP001-002-S003',
            subtitle: '动力舱',
            targetPath: '/projects/8/shots/31'
          }],
          hasMore: false
        },
        assets: { items: [], hasMore: false },
        files: { items: [], hasMore: false }
      }
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.useRealTimers()
  })

  it('输入不足两个字符不请求，达到长度后 250ms 防抖搜索', async () => {
    const wrapper = mountDialog()
    const input = document.body.querySelector('input[aria-label="全局搜索关键字"]')

    input.value = 'E'
    input.dispatchEvent(new Event('input'))
    await vi.advanceTimersByTimeAsync(300)
    expect(searchShotGrid).not.toHaveBeenCalled()

    input.value = 'EP001'
    input.dispatchEvent(new Event('input'))
    await vi.advanceTimersByTimeAsync(249)
    expect(searchShotGrid).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    await flushPromises()

    expect(searchShotGrid).toHaveBeenCalledWith('EP001', expect.objectContaining({
      limit: 8,
      signal: expect.any(AbortSignal)
    }))
    expect(document.body.textContent).toContain('EP001-002-S003')
    const projectTag = wrapper.findComponent(ElTag)
    expect(projectTag.text()).toBe('LCFR · 罗刹夫人')
    expect(projectTag.props()).toMatchObject({ type: 'info', effect: 'plain', size: 'small', round: true })
    wrapper.unmount()
  })

  it('点击结果关闭弹窗并进入后端返回的业务详情路由', async () => {
    const wrapper = mountDialog()
    const input = document.body.querySelector('input[aria-label="全局搜索关键字"]')
    input.value = '动力舱'
    input.dispatchEvent(new Event('input'))
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()

    const result = document.body.querySelector('.search-result')
    result.click()
    await flushPromises()

    expect(push).toHaveBeenCalledWith('/projects/8/shots/31')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
    wrapper.unmount()
  })

  it('关键字变化时取消尚未完成的旧请求', async () => {
    searchShotGrid.mockImplementation(() => new Promise(() => {}))
    const wrapper = mountDialog()
    const input = document.body.querySelector('input[aria-label="全局搜索关键字"]')
    input.value = '动力舱'
    input.dispatchEvent(new Event('input'))
    await vi.advanceTimersByTimeAsync(250)
    const firstSignal = searchShotGrid.mock.calls[0][1].signal

    input.value = '动力舱镜头'
    input.dispatchEvent(new Event('input'))
    await wrapper.vm.$nextTick()

    expect(firstSignal.aborted).toBe(true)
    wrapper.unmount()
  })

  it('权限中只有镜头列表时仅展示镜头分组', async () => {
    const wrapper = mountDialog(['shotgrid:shot:list', 'shotgrid:shot:query'])
    const input = document.body.querySelector('input[aria-label="全局搜索关键字"]')
    input.value = '动力舱'
    input.dispatchEvent(new Event('input'))
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()

    expect(document.body.textContent).toContain('镜头')
    expect(document.body.textContent).not.toContain('资产')
    expect(document.body.textContent).not.toContain('文件')
    wrapper.unmount()
  })
})
