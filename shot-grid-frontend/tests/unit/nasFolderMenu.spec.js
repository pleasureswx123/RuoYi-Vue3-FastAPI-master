import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NasFolderMenu from '@/components/NasFolderMenu.vue'
import { getVersionDetail, getNasOpenTicket } from '@/api/shot-grid/versions'
vi.mock('@/api/shot-grid/versions', () => ({ getVersionDetail: vi.fn(), getNasOpenTicket: vi.fn(), getNasOpenerPublicKey: vi.fn() }))
const row = { rowKind: 'item', task: { taskId: 2 }, latestVersion: { versionId: 3 } }
function render(canQuery = true) {
  return mount(NasFolderMenu, { props: { projectId: 7, canQuery }, global: { directives: { loading: {} }, stubs: {
    ElPopover: { props: ['visible'], template: '<div v-if="visible"><slot /></div>' },
    ElDialog: { props: ['modelValue'], template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>' },
    ElButton: { template: '<button><slot /></button>' }, ElAlert: { props: ['title'], template: '<p>{{ title }}</p>' },
    ElForm: { template: '<div><slot /></div>' }, ElFormItem: { template: '<div><slot /></div>' },
    ElSelect: { template: '<div><slot /></div>' }, ElOption: true, ElInput: true, ElLink: true
  } } })
}
function context(wrapper, value = row) {
  const event = { preventDefault: vi.fn(), clientX: 10, clientY: 20 }
  wrapper.vm.open(value, null, event)
  return event
}
beforeEach(() => { vi.clearAllMocks(); getNasOpenTicket.mockImplementation(() => Promise.resolve({ data: { folder: '\\\\192.168.10.64\\share\\project', uri: 'shotgrid-nas://open-v1/YQ.Yg' } })) })
describe('列表 NAS 右键入口', () => {
  it('真实菜单单目录直接发起签名请求且不显示浮动提示', async () => {
    const path = '\\\\192.168.10.64\\share\\project'
    getVersionDetail.mockResolvedValue({ data: { projectId: 7, taskId: 2, versionId: 3, files: [{ fileId: '00000000-0000-4000-8000-000000000001', nasPath: path + '\\a.jpg' }] } })
    const wrapper = mount(NasFolderMenu, { attachTo: document.body, props: { projectId: 7, canQuery: true } })
    context(wrapper)
    await flushPromises()
    const button = document.querySelector('.nas-folder-popover button')
    expect(button).not.toBeNull()
    button.click()
    await flushPromises()
    expect(getNasOpenTicket).toHaveBeenCalled()
    expect(document.querySelector('.nas-open-fallback')).toBeNull()
    expect(document.querySelector('.el-dialog')).toBeNull()
    wrapper.unmount()
  })
  it('无查询权限与资产父行不接管右键', () => {
    const wrapper = render(false)
    expect(context(wrapper).preventDefault).not.toHaveBeenCalled()
    wrapper.unmount()
    const allowed = render()
    expect(context(allowed, { rowKind: 'asset' }).preventDefault).not.toHaveBeenCalled()
    allowed.unmount()
  })
  it.each([row, { taskId: 2, latestVersion: { versionId: 3 } }])('镜头和分项点击菜单后才请求鉴权路径', async value => {
    getVersionDetail.mockResolvedValue({ data: { projectId: 7, taskId: 2, versionId: 3, files: [{ fileId: '00000000-0000-4000-8000-000000000001', nasPath: '\\\\192.168.10.64\\share\\project\\a.jpg' }] } })
    const wrapper = render()
    context(wrapper, value)
    await flushPromises()
    expect(getVersionDetail).not.toHaveBeenCalled()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(getVersionDetail).toHaveBeenCalledWith(3, { signal: expect.any(AbortSignal) })
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('section').exists()).toBe(false)
    wrapper.unmount()
  })
  it('切换项目后取消请求并隔离迟到响应', async () => {
    let resolve
    getVersionDetail.mockReturnValue(new Promise(done => { resolve = done }))
    const wrapper = render()
    context(wrapper)
    await flushPromises()
    await wrapper.get('button').trigger('click')
    const signal = getVersionDetail.mock.calls[0][1].signal
    await wrapper.setProps({ projectId: 8 })
    expect(signal.aborted).toBe(true)
    resolve({ data: { projectId: 7, taskId: 2, versionId: 3, files: [] } })
    await flushPromises()
    expect(wrapper.find('section').exists()).toBe(false)
    wrapper.unmount()
  })
  it('没有版本时不请求不存在的版本', async () => {
    const wrapper = render()
    context(wrapper, { taskId: 2 })
    await flushPromises()
    await wrapper.get('button').trigger('click')
    expect(wrapper.text()).toContain('尚无已发布版本')
    expect(getVersionDetail).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('多个目录只选择，不自动发起打开', async () => {
    getVersionDetail.mockResolvedValue({ data: { projectId: 7, taskId: 2, versionId: 3, files: [
      { fileId: 'a', nasPath: '\\\\192.168.10.64\\share\\one\\a.png' },
      { fileId: 'b', nasPath: '\\\\192.168.10.64\\share\\two\\b.png' }
    ] } })
    const wrapper = render()
    context(wrapper)
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(getNasOpenTicket).not.toHaveBeenCalled()
    expect(wrapper.find('section').exists()).toBe(true)
    wrapper.unmount()
  })
  it('签名接口失败仍提供目录复制和安装入口', async () => {
    getVersionDetail.mockResolvedValue({ data: { projectId: 7, taskId: 2, versionId: 3, files: [{ fileId: 'a', nasPath: '\\\\192.168.10.64\\share\\project\\a.png' }] } })
    getNasOpenTicket.mockRejectedValue(new Error('签名服务未配置'))
    const wrapper = render()
    context(wrapper)
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('签名服务未配置')
    expect(wrapper.text()).toContain('复制目录')
    expect(wrapper.text()).toContain('下载 Windows 安装工具')
    wrapper.unmount()
  })
  it('签名返回其他目录时拒绝启动', async () => {
    getVersionDetail.mockResolvedValue({ data: { projectId: 7, taskId: 2, versionId: 3, files: [{ fileId: 'a', nasPath: '\\\\192.168.10.64\\share\\project\\a.png' }] } })
    getNasOpenTicket.mockResolvedValue({ data: { folder: 'other', uri: 'shotgrid-nas://open-v1/YQ.Yg' } })
    const wrapper = render()
    context(wrapper)
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('打开凭证不符合安全规则')
    expect(wrapper.find('aside').exists()).toBe(false)
    wrapper.unmount()
  })

  it('右键帮助仍可展示安装与复制入口，不自动启动工具', async () => {
    getVersionDetail.mockResolvedValue({ data: { projectId: 7, taskId: 2, versionId: 3, files: [{ fileId: 'a', nasPath: '\\\\192.168.10.64\\share\\project\\a.png' }] } })
    const wrapper = render()
    context(wrapper)
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '安装／打开帮助').trigger('click')
    await flushPromises()
    expect(wrapper.find('section').exists()).toBe(true)
    expect(wrapper.text()).toContain('复制目录')
    expect(wrapper.text()).toContain('下载 Windows 安装工具')
    expect(getNasOpenTicket).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
