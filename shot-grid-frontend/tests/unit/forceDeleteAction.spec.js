import { mount, flushPromises } from '@vue/test-utils'
import { ElButton } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ForceDeleteAction from '@/components/ForceDeleteAction.vue'
import { batchForceDeleteShots } from '@/api/shot-grid/shots'

vi.mock('@/store/modules/session', () => ({ useSessionStore: () => ({ permissions: ['shotgrid:shot:forceDelete', 'shotgrid:asset:forceDelete'] }) }))
vi.mock('@/api/shot-grid/shots', () => ({ batchForceDeleteShots: vi.fn() }))
vi.mock('@/api/shot-grid/assets', () => ({ batchForceDeleteAssets: vi.fn() }))
let wrapper
afterEach(() => { wrapper?.unmount(); vi.clearAllMocks() })
const items = [{ shotId: 7, lockVersion: 3, allowedActions: ['shot.forceDelete'] }]
function button(text) { return wrapper.findAllComponents(ElButton).find(item => item.text().includes(text)) }
async function open() {
  wrapper = mount(ForceDeleteAction, { props: { projectId: 1, entityType: 'shot', items }, attachTo: document.body, global: { stubs: { teleport: true } } })
  await button('强制删除镜头').trigger('click')
  await flushPromises()
}
describe('强制删除交互', () => {
  it.each(['shot', 'asset'])('父表格重绘同一 %s 时保持弹窗及已填原因，切换目标才关闭', async (entityType) => {
    const target = { [`${entityType}Id`]: 7, lockVersion: 3, allowedActions: [`${entityType}.forceDelete`] }
    wrapper = mount(ForceDeleteAction, { props: { projectId: 1, entityType, items: [target] }, attachTo: document.body, global: { stubs: { teleport: true } } })
    await wrapper.findComponent(ElButton).trigger('click')
    await flushPromises()
    await wrapper.get('textarea').setValue('保留已填原因')
    await wrapper.setProps({ items: [{ ...target }] })
    await flushPromises()
    expect(wrapper.vm.visible).toBe(true)
    expect(wrapper.get('textarea').element.value).toBe('保留已填原因')
    await wrapper.setProps({ items: [{ ...target, [`${entityType}Id`]: 8 }] })
    expect(wrapper.vm.visible).toBe(false)
  })
  it('拒绝空白原因，校验成功后发送目标锁版本与原因', async () => {
    batchForceDeleteShots.mockResolvedValue({ data: {} })
    await open()
    expect(wrapper.text()).toContain('此操作不可恢复')
    expect(wrapper.text()).not.toContain('保留历史记录')
    await button('确认强制删除').trigger('click')
    await flushPromises()
    expect(batchForceDeleteShots).not.toHaveBeenCalled()
    await wrapper.get('textarea').setValue(' 清理测试 ')
    await button('确认强制删除').trigger('click')
    await flushPromises()
    expect(batchForceDeleteShots).toHaveBeenCalledExactlyOnceWith(1, [{ shotId: 7, lockVersion: 3 }], '清理测试')
    expect(wrapper.emitted('deleted')).toHaveLength(1)
  })
  it('切换项目后取消旧目标提交', async () => {
    await open()
    await wrapper.setProps({ projectId: 2 })
    await flushPromises()
    expect(wrapper.vm.visible).toBe(false)
    expect(batchForceDeleteShots).not.toHaveBeenCalled()
  })
  it('没有目标动作授权时隐藏入口', async () => {
    wrapper = mount(ForceDeleteAction, { props: { projectId: 1, entityType: 'shot', items: [{ shotId: 7, allowedActions: [] }] } })
    expect(button('强制删除镜头')).toBeUndefined()
  })
})
