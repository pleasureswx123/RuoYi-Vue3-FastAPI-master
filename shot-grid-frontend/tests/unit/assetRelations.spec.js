import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElButton, ElForm, ElSelect } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/store/modules/session'
import AssetRelationsPanel from '@/views/asset/components/AssetRelationsPanel.vue'
import AssetRelationSelect from '@/views/asset/components/AssetRelationSelect.vue'
import AssetFormDialog from '@/views/asset/components/AssetFormDialog.vue'
import { getAssetRelations, updateAssetRelations, getAssetPage, createAsset, getAssetDetail } from '@/api/shot-grid/assets'
import { getShotDetail } from '@/api/shot-grid/shots'
vi.mock('@/api/shot-grid/shots', () => ({ getShotDetail: vi.fn() }))
vi.mock('@/api/shot-grid/assets', () => ({ getAssetRelations: vi.fn(), updateAssetRelations: vi.fn(), getAssetPage: vi.fn(), createAsset: vi.fn(), updateAsset: vi.fn(), getAssetDetail: vi.fn() }))
const open = vi.fn()
const target = { assetId: 2, projectId: 8, assetName: '小明', assetType: 'Character', lifecycleStatus: 'active', items: [{ assetItemId: 20, productionItem: '正面', assetStatus: 'completed', task: { assigneeName: 'A' }, version: { versionId: 71, versionNo: 1, versionStatus: 'final' } }] }
const response = () => ({ projectId: 8, assetId: 1, lockVersion: 3, canEdit: true, relatedAssets: [structuredClone(target)] })
async function mountPanel(permissions = ['*:*:*']) {
  const pinia = createPinia(); setActivePinia(pinia); useSessionStore().permissions = permissions
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }, { path: '/projects/:projectId/assets/:assetId', component: { template: '<div />' } }] })
  await router.push('/'); await router.isReady()
  const wrapper = mount(AssetRelationsPanel, { props: { projectId: 8, assetId: 1 }, global: { plugins: [pinia, router], stubs: { RelatedDetailDrawer: { name: 'RelatedDetailDrawer', methods: { open }, template: '<div />' } } } })
  await flushPromises()
  return wrapper
}
const button = (wrapper, text) => wrapper.findAllComponents(ElButton).find(item => item.text() === text)
beforeEach(() => {
  getAssetRelations.mockResolvedValue({ data: response() })
  updateAssetRelations.mockResolvedValue({ data: response() })
  getAssetPage.mockResolvedValue({ rows: [{ ...target, items: undefined }], hasNext: false })
})
describe('资产关联资料', () => {
  it('关联资料区分已通过可用、制作中与暂无成果，制作人不显示管理入口', async () => {
    const data = response()
    data.relatedAssets[0].items.push(
      { assetItemId: 21, productionItem: '背面', assetStatus: 'in_progress', task: { assigneeName: 'B' }, version: null },
      { assetItemId: 22, productionItem: '侧面', assetStatus: 'unassigned', task: null, version: null }
    )
    getAssetRelations.mockResolvedValueOnce({ data })
    const wrapper = await mountPanel(['shotgrid:asset:query', 'shotgrid:version:query'])
    expect(wrapper.text()).toContain('已通过可用')
    expect(wrapper.text()).toContain('制作中 · 暂无成果')
    expect(wrapper.text()).toContain('暂无成果')
    expect(button(wrapper, '调整关联')).toBeUndefined()
    wrapper.unmount()
  })
  it('镜头关联复用鉴权详情、优先已通过成果，读取失败可见且不开放编辑', async () => {
    const wrapper = await mountPanel()
    getShotDetail.mockResolvedValue({ data: { projectId: 8, shotId: 7, assets: [target, { ...target, assetId: 3 }] } })
    getAssetDetail.mockImplementation((_project, id) => id === 3 ? Promise.reject(new Error('素材读取失败')) : Promise.resolve({ data: { ...target, items: [{ ...target.items[0], lifecycleStatus: 'active', finalVersion: target.items[0].version, latestVersion: { versionId: 72, versionStatus: 'pending_review' } }] } }))
    try {
      await wrapper.setProps({ shotId: 7 }); await flushPromises()
      expect(wrapper.text()).toContain('已通过成果')
      expect(wrapper.text()).toContain('素材读取失败')
      expect(button(wrapper, '调整关联')).toBeUndefined()
      await button(wrapper, '查看成果').trigger('click'); expect(open).toHaveBeenCalledWith('/versions/71')
      getShotDetail.mockResolvedValue({ data: { projectId: 9, shotId: 8, assets: [target] } })
      await wrapper.setProps({ shotId: 8 }); await flushPromises()
      expect(wrapper.text()).toContain('镜头关联归属不匹配')
      expect(wrapper.text()).not.toContain('已通过成果')
    } finally { wrapper.unmount() }
  })
  it('按类型展示负责人和成果，未通过明确标注并走原版本详情', async () => {
    const data = response()
    data.relatedAssets.push({ ...structuredClone(target), assetId: 3, assetName: '汽车', assetType: 'Prop', items: [{ ...target.items[0], assetItemId: 30, version: { versionId: 72, versionNo: 2, versionStatus: 'pending_review' } }] })
    getAssetRelations.mockResolvedValueOnce({ data })
    const wrapper = await mountPanel()
    try {
      expect(wrapper.text()).toContain('角色 · 1')
      expect(wrapper.text()).toContain('道具 · 1')
      expect(wrapper.text()).toContain('制作人：A')
      expect(wrapper.text()).toContain('已通过成果')
      expect(wrapper.text()).toContain('未通过，仅供参考')
      await button(wrapper, '查看成果').trigger('click')
      expect(open).toHaveBeenCalledWith('/versions/71')
    } finally { wrapper.unmount() }
  })
  it('修改关联先校验，再带原锁保存，移除不调用删除资产', async () => {
    const wrapper = await mountPanel()
    try {
      await button(wrapper, '调整关联').trigger('click')
      const select = wrapper.getComponent(AssetRelationSelect)
      select.vm.$emit('update:modelValue', [1]); await flushPromises()
      await button(wrapper, '保存关联').trigger('click'); await flushPromises()
      expect(updateAssetRelations).not.toHaveBeenCalled()
      await vi.waitFor(() => expect(wrapper.text()).toContain('请选择有效且不重复'))
      select.vm.$emit('update:modelValue', []); await flushPromises()
      await button(wrapper, '保存关联').trigger('click'); await flushPromises()
      expect(updateAssetRelations).toHaveBeenCalledWith(8, 1, { relatedAssetIds: [], lockVersion: 3 })
      expect(wrapper.emitted('updated')).toHaveLength(1)
    } finally { wrapper.unmount() }
  })
  it('结果未知保留选择且阻止重复提交，保存中不能离开', async () => {
    let reject
    updateAssetRelations.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
    const wrapper = await mountPanel()
    try {
      await button(wrapper, '调整关联').trigger('click')
      wrapper.getComponent(AssetRelationSelect).vm.$emit('update:modelValue', []); await flushPromises()
      await button(wrapper, '保存关联').trigger('click'); await flushPromises()
      expect(await wrapper.vm.$.exposed.canLeave()).toBe(false)
      expect(button(wrapper, '保存关联').props('loading')).toBe(true)
      reject({ status: 503 }); await flushPromises()
      expect(wrapper.getComponent(AssetRelationSelect).props('modelValue')).toEqual([])
      expect(wrapper.text()).toContain('保存结果需核对')
      expect(button(wrapper, '保存关联').props('disabled')).toBe(true)
    } finally { wrapper.unmount() }
  })
  it('权限控制读取与编辑，归属不符失败关闭', async () => {
    let wrapper = await mountPanel(['shotgrid:asset:query'])
    expect(button(wrapper, '调整关联')).toBeUndefined()
    expect(button(wrapper, '查看成果').props('disabled')).toBe(true)
    wrapper.unmount()
    getAssetRelations.mockClear()
    wrapper = await mountPanel([])
    expect(getAssetRelations).not.toHaveBeenCalled()
    wrapper.unmount()
    getAssetRelations.mockResolvedValueOnce({ data: { ...response(), projectId: 9 } })
    wrapper = await mountPanel()
    expect(wrapper.text()).toContain('关联资料归属不匹配')
    expect(wrapper.text()).not.toContain('小明')
    wrapper.unmount()
  })
  it('切换任务取消旧关联请求，迟到数据不会进入新任务', async () => {
    let finish
    getAssetRelations.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await mountPanel()
    try {
      const signal = getAssetRelations.mock.calls[0][2].signal
      getAssetRelations.mockResolvedValueOnce({ data: { ...response(), assetId: 4, relatedAssets: [] } })
      await wrapper.setProps({ assetId: 4 }); await flushPromises()
      finish({ data: response() }); await flushPromises()
      expect(signal.aborted).toBe(true)
      expect(wrapper.text()).not.toContain('小明')
      expect(wrapper.text()).toContain('暂未关联资产')
    } finally { wrapper.unmount() }
  })
  it('选择器支持分页，排除自身及归档对象并隔离迟到搜索', async () => {
    getAssetPage.mockResolvedValueOnce({ rows: [target, { ...target, assetId: 1 }, { ...target, assetId: 3, lifecycleStatus: 'archived' }], hasNext: true })
    const wrapper = mount(AssetRelationSelect, { props: { projectId: 8, assetId: 1, modelValue: [] } })
    try {
      wrapper.getComponent(ElSelect).vm.$emit('visible-change', true); await flushPromises()
      expect(wrapper.findAllComponents({ name: 'ElOption' }).map(item => item.props('value'))).toEqual([2])
      getAssetPage.mockResolvedValueOnce({ rows: [{ ...target, assetId: 4 }], hasNext: false })
      await button(wrapper, '加载更多资产').trigger('click'); await flushPromises()
      expect(getAssetPage.mock.lastCall[1].pageNum).toBe(2)
      expect(wrapper.findAllComponents({ name: 'ElOption' }).map(item => item.props('value'))).toEqual([2, 4])
    } finally { wrapper.unmount() }
  })
  it('新建资产把预选关联与制作分项一起提交', async () => {
    createAsset.mockResolvedValue({ data: { assetId: 10 } })
    const wrapper = mount(AssetFormDialog, { props: { projectId: 8, operationGeneration: 1, canLink: true } })
    try {
      await flushPromises()
      const form = wrapper.getComponent(ElForm).props('model')
      form.assetName = '街道'
      wrapper.getComponent(AssetRelationSelect).vm.$emit('update:modelValue', [2]); await flushPromises()
      const submit = wrapper.findAllComponents(ElButton).find(item => item.props('type') === 'primary' && !item.props('link'))
      await submit.trigger('click'); await flushPromises()
      expect(createAsset.mock.lastCall[1]).toMatchObject({ assetName: '街道', relatedAssetIds: [2], items: [{ productionItem: '基础设定' }] })
    } finally { wrapper.unmount() }
  })
})
