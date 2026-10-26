import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/store/modules/session'
import NasOpenButton from '@/components/NasOpenButton.vue'

const { openTarget } = vi.hoisted(() => ({ openTarget: vi.fn() }))
vi.mock('@/components/NasFolderMenu.vue', () => ({ default: {
  props: ['projectId', 'canQuery'],
  setup(_props, { expose }) { expose({ openTarget }); return {} },
  template: '<div data-testid="opener" />'
} }))
beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('NAS 打开按钮', () => {
  it('版本入口按查询权限显隐，点击后传递精确文件目标', async () => {
    const wrapper = mount(NasOpenButton, { props: { projectId: 7, taskId: 2, versionId: 3, fileId: 'file-b' } })
    expect(wrapper.find('button').exists()).toBe(false)
    useSessionStore().permissions = ['shotgrid:version:query']
    await flushPromises()
    expect(wrapper.find('[data-testid="opener"]').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(openTarget).toHaveBeenCalledWith({ kind: 'version', taskId: 2, versionId: 3, fileId: 'file-b' })
    await wrapper.setProps({ versionId: 4 })
    expect(wrapper.find('[data-testid="opener"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('存储权限只启用项目入口，禁用状态不能触发', async () => {
    useSessionStore().permissions = ['shotgrid:storage:path']
    const wrapper = mount(NasOpenButton, { props: { projectId: 7, kind: 'project', disabled: true } })
    expect(wrapper.get('button').element.disabled).toBe(true)
    await wrapper.get('button').trigger('click')
    expect(openTarget).not.toHaveBeenCalled()
    await wrapper.setProps({ disabled: false })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(openTarget).toHaveBeenCalledWith({ kind: 'project', taskId: 0, versionId: 0, fileId: '' })
    await wrapper.setProps({ kind: 'version' })
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })
})
