import { mount, flushPromises, DOMWrapper } from '@vue/test-utils'
import { ElButton, ElCheckboxGroup, ElRadioGroup, ElSteps, ElDrawer, ElInputNumber, ElCollapse } from 'element-plus'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import ProductionAdjustmentDialog from '@/views/shot/components/ProductionAdjustmentDialog.vue'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { uploadReviewReferenceFile } from '@/api/shot-grid/reviews'
import ProductionAdjustmentField from '@/views/shot/components/ProductionAdjustmentField.vue'
import { getShotDetail } from '@/api/shot-grid/shots'
import { adjustShotProduction, getTaskDetail } from '@/api/shot-grid/tasks'

vi.mock('@/api/shot-grid/reviews', () => ({ uploadReviewReferenceFile: vi.fn(), downloadReviewReferenceFile: vi.fn() }))
vi.mock('@/api/shot-grid/shots', () => ({ getShotDetail: vi.fn() }))
vi.mock('@/api/shot-grid/tasks', () => ({ adjustShotProduction: vi.fn(), getTaskDetail: vi.fn() }))
const shots = [1, 2].map(id => ({ shotId: id, taskId: id + 10, shotCode: `000${id}`, taskLockVersion: 3, lockVersion: 2 }))
let wrapper
const context = (overrides = {}) => ({ projectId: 8, shots, permissions: ['*:*:*'], members: [{ userId: 7, userName: '制作人甲' }, { userId: 8, userName: '制作人乙' }], validateContext: () => true, ...overrides })
async function open(overrides) {
  wrapper = mount(ProductionAdjustmentDialog, { props: { context: context(overrides) } })
  await flushPromises()
}
const button = text => wrapper.findAllComponents(ElButton).find(item => item.text() === text)
async function click(text) { await button(text).trigger('click'); await flushPromises() }
const stage = () => wrapper.getComponent(ElSteps).props('active')
async function choose(keys) {
  wrapper.getComponent(ElCheckboxGroup).vm.$emit('update:modelValue', keys)
  await flushPromises()
}

async function setValue(key, value, index = 0) {
  wrapper.findAllComponents(ProductionAdjustmentField).filter(item => item.props('field').key === key)[index].vm.$emit('update:modelValue', value)
  await flushPromises()
}
async function reason() { await new DOMWrapper(document.body).get('textarea[placeholder="说明与制作人沟通后的调整原因"]').setValue('已与制作人沟通') }
beforeEach(() => {
  vi.clearAllMocks()
  uploadReviewReferenceFile.mockReset().mockResolvedValue({ fileId: '11111111-1111-4111-8111-111111111111' })
  getTaskDetail.mockResolvedValue({ data: { lockVersion: 3, referenceFiles: [] } })
  adjustShotProduction.mockReset().mockResolvedValue({ data: { updatedCount: 2 } })
  getShotDetail.mockReset().mockImplementation((_project, id) => Promise.resolve({ data: {
    shotId: id, lockVersion: 2, allowedActions: ['task.adjust'], description: `内容${id}`, durationMs: 2000,
    task: { taskId: id+10, lockVersion: 3, priority: 'normal', assignee: { userId: 7 }, expectedStartTime: '2026-09-28T09:00:00', expectedEndTime: '2026-10-01T18:00:00' }
  } }))
})
afterEach(() => { wrapper?.unmount(); wrapper = null })

describe('制作任务调整', () => {
  it('单镜头直接编辑且只发送变化字段，缺少旧排期不阻止修改内容', async () => {
    getShotDetail.mockResolvedValue({ data: { shotId: 1, lockVersion: 2, allowedActions: ['task.adjust'], description: '原内容', durationMs: 5000, task: { taskId: 11, lockVersion: 3, assignee: { userId: 7 }, priority: 'normal' } } })
    await open({ shots: [shots[0]] })
    expect(wrapper.findComponent(ElSteps).exists()).toBe(false)
    expect(wrapper.findComponent(ElCheckboxGroup).exists()).toBe(false)
    expect(wrapper.getComponent(ElDrawer).props('size')).toBe('min(620px, 100vw)')
    expect(wrapper.getComponent(ElCollapse).props('modelValue')).toEqual([])
    expect(button('保存修改').props('disabled')).toBe(true)
    await setValue('description', '新的制作内容')
    await click('保存修改')
    expect(adjustShotProduction).toHaveBeenCalledWith(8, { reason: '', items: [{ ...{ shotId: 1, taskId: 11, lockVersion: 3, shotLockVersion: 2 }, changes: { description: '新的制作内容' } }] })
    expect(wrapper.emitted('close')).toEqual([[{ saved: true }]])
  })

  it('秒输入转换为整数毫秒，恢复原值后无需保存', async () => {
    await open({ shots: [shots[0]] })
    const duration = wrapper.getComponent(ElInputNumber)
    expect(duration.props('modelValue')).toBe(2)
    duration.vm.$emit('update:modelValue', 2.125)
    await flushPromises()
    expect(button('保存修改').props('disabled')).toBe(false)
    duration.vm.$emit('update:modelValue', 2)
    await flushPromises()
    expect(button('保存修改').props('disabled')).toBe(true)
    duration.vm.$emit('update:modelValue', 2.125)
    await flushPromises(); await click('保存修改')
    expect(adjustShotProduction.mock.calls[0][1].items[0].changes).toEqual({ durationMs: 2125 })
  })

  it('单镜头修改后的非法时间或空时长无法提交，修正后可保存', async () => {
    await open({ shots: [shots[0]] })
    await setValue('expectedRange', null)
    await setValue('durationMs', undefined)
    await click('保存修改')
    expect(adjustShotProduction).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(document.body.textContent).toContain('请选择完整且结束晚于开始的计划时间'))
    await setValue('expectedRange', ['2026-11-01T09:00:00', '2026-11-02T18:00:00'])
    await setValue('durationMs', 3000)
    await click('保存修改')
    expect(adjustShotProduction).toHaveBeenCalledTimes(1)
  })

  it('单镜头权限过滤不因直接编辑而扩大，已有参考只展示并追加新说明', async () => {
    getTaskDetail.mockResolvedValue({ data: { lockVersion: 3, referenceDescription: '已有参考说明', referenceFiles: [] } })
    await open({ shots: [shots[0]], permissions: ['shotgrid:shot:edit'] })
    const keys = wrapper.findAllComponents(ProductionAdjustmentField).map(item => item.props('field').key)
    expect(keys).not.toContain('assigneeUserId')
    expect(keys).not.toContain('expectedRange')
    expect(keys).not.toContain('priority')
    expect(document.body.textContent).toContain('已有参考说明')
    await new DOMWrapper(document.body).get('textarea[aria-label="参考说明"]').setValue('补充光线参考')
    await click('保存修改')
    expect(adjustShotProduction.mock.calls[0][1].items[0].changes).toEqual({ referenceDescription: '补充光线参考' })
  })

  it('单镜头保存期间禁止重复提交，冲突后保留结果保护', async () => {
    let reject
    adjustShotProduction.mockImplementation(() => new Promise((_resolve, failure) => { reject = failure }))
    await open({ shots: [shots[0]] }); await setValue('description', '修改内容')
    await click('保存修改')
    expect(button('保存修改').props('loading')).toBe(true)
    await click('保存修改')
    expect(adjustShotProduction).toHaveBeenCalledTimes(1)
    reject({ httpStatus: 409, message: '任务已变化' }); await flushPromises()
    expect(button('保存修改')).toBeUndefined()
    expect(document.body.textContent).toContain('任务已变化')
  })

  it('单镜头未修改可直接取消，不要求放弃修改确认', async () => {
    await open({ shots: [shots[0]] }); await click('取消')
    expect(wrapper.emitted('close')).toEqual([[{ attempted: false }]])
    expect(adjustShotProduction).not.toHaveBeenCalled()
  })

  it('单镜头快捷编辑备注会展开更多信息，清空原文本仅提交该字段', async () => {
    await open({ shots: [shots[0]], initialFields: ['remark'] })
    expect(wrapper.getComponent(ElCollapse).props('modelValue')).toEqual(['more'])
    await setValue('description', '')
    await click('保存修改')
    expect(adjustShotProduction.mock.calls[0][1].items[0].changes).toEqual({ description: null })
  })

  it('批量制作人入口预选负责人，保存只提交负责人字段，重置保留预选', async () => {
    await open({ initialFields: ['assigneeUserId'] })
    expect(wrapper.getComponent(ElCheckboxGroup).props('modelValue')).toEqual(['assigneeUserId'])
    await click('重置')
    expect(wrapper.getComponent(ElCheckboxGroup).props('modelValue')).toEqual(['assigneeUserId'])
    await setValue('assigneeUserId', 8)
    await click('下一步：核对修改'); await click('应用到 2 个镜头')
    expect(adjustShotProduction.mock.calls[0][1].items.map(row => row.changes)).toEqual([{ assigneeUserId: 8 }, { assigneeUserId: 8 }])
  })

  it('预选字段仍按当前权限过滤，不增加改派授权', async () => {
    await open({ permissions: ['shotgrid:task:edit'], initialFields: ['assigneeUserId'] })
    expect(wrapper.getComponent(ElCheckboxGroup).props('modelValue')).toEqual([])
    expect(wrapper.findAllComponents(ProductionAdjustmentField).some(item => item.props('field').key === 'assigneeUserId')).toBe(false)
  })
  it('参考资料仅上传一次并追加到全部所选任务，上传失败保持可重试', async () => {
    await open()
    await choose(['referenceFileIds'])
    await reason()
    await click('下一步：核对修改')
    expect(stage()).toBe(0)
    wrapper.getComponent(ReviewReferenceInput).vm.$emit('add', { raw: new File(['参考'], '参考.pdf', { type: 'application/pdf' }) })
    await flushPromises()
    await click('下一步：核对修改')
    expect(stage()).toBe(1)
    expect(document.body.textContent).toContain('参考.pdf')
    uploadReviewReferenceFile.mockRejectedValueOnce(new Error('上传失败'))
    await click('应用到 2 个镜头')
    expect(adjustShotProduction).not.toHaveBeenCalled()
    await click('应用到 2 个镜头')
    expect(adjustShotProduction.mock.calls[0][1].items.map(item => item.changes)).toEqual([
      { referenceFileIds: ['11111111-1111-4111-8111-111111111111'] },
      { referenceFileIds: ['11111111-1111-4111-8111-111111111111'] }
    ])
    expect(uploadReviewReferenceFile).toHaveBeenCalledTimes(2)
  })
  it('累计超过五个时不能进入保存预览', async () => {
    getTaskDetail.mockResolvedValue({ data: { lockVersion: 3, referenceFiles: Array.from({ length: 5 }, (_, i) => ({ fileId: String(i), originalName: `已有${i}.pdf` })) } })
    await open(); await choose(['referenceFileIds']); await reason()
    wrapper.getComponent(ReviewReferenceInput).vm.$emit('add', { raw: new File(['参考'], '参考.pdf') })
    await flushPromises(); await click('下一步：核对修改')
    expect(stage()).toBe(0)
    await vi.waitFor(() => expect(document.body.textContent).toContain('超过 5 个'))
    expect(adjustShotProduction).not.toHaveBeenCalled()
  })
  it('参考字段放在最后，纯文字说明可批量追加并进入核对', async () => {
    await open()
    expect(wrapper.getComponent(ElDrawer).props('direction')).toBe('rtl')
    expect(wrapper.getComponent(ElCheckboxGroup).text()).toContain('参考内容（可选）')
    await choose(['referenceFileIds']); await reason()
    await new DOMWrapper(document.body).get('textarea[aria-label="参考说明"]').setValue('参考影片的暖色光线')
    await click('下一步：核对修改')
    expect(stage()).toBe(1)
    expect(document.body.textContent).toContain('参考影片的暖色光线')
    await click('应用到 2 个镜头')
    expect(adjustShotProduction.mock.calls[0][1].items.every(item => item.changes.referenceDescription === '参考影片的暖色光线' && !('referenceFileIds' in item.changes))).toBe(true)
  })
  it('默认不修改任何字段，原因选填直接预览；明确清空且只发送勾选字段', async () => {
    await open()
    await click('下一步：核对修改')
    expect(stage()).toBe(0)
    await choose(['priority', 'description'])
    await setValue('priority', 'high')
    await setValue('description', '')
    await click('下一步：核对修改')
    expect(stage()).toBe(1)
    expect(document.body.textContent).toContain('内容1')
    expect(document.body.textContent).toContain('将清空')
    await click('应用到 2 个镜头')
    expect(adjustShotProduction).toHaveBeenCalledWith(8, { reason: '', items: shots.map(shot => ({ taskId: shot.taskId, shotId: shot.shotId, lockVersion: 3, shotLockVersion: 2, changes: { priority: 'high', description: null } })) })
    expect(wrapper.emitted('close')).toEqual([[{ saved: true }]])
  })
  it('逐镜头填写不同制作内容，前后切换保留；重置清空选择', async () => {
    await open()
    await choose(['description'])
    wrapper.getComponent(ElRadioGroup).vm.$emit('update:modelValue', 'individual')
    await flushPromises()
    await setValue('description', '新内容甲', 0)
    await setValue('description', '新内容乙', 1)
    await reason()
    await click('下一步：核对修改')
    expect(document.body.textContent).toContain('新内容甲')
    expect(document.body.textContent).toContain('新内容乙')
    await click('返回编辑')
    expect(wrapper.findAllComponents(ProductionAdjustmentField).map(item => item.props('modelValue'))).toEqual(['新内容甲', '新内容乙'])
    await click('下一步：核对修改')
    await click('应用到 2 个镜头')
    expect(adjustShotProduction.mock.calls[0][1].items.map(item => item.changes.description)).toEqual(['新内容甲', '新内容乙'])
  })
  it('时间必须完整有序、数值不能清空，制作信息权限限制可选字段', async () => {
    await open({ permissions: ['shotgrid:task:edit', 'shotgrid:task:schedule'] })
    expect(wrapper.getComponent(ElCheckboxGroup).text()).not.toContain('制作内容')
    expect(wrapper.getComponent(ElCheckboxGroup).text()).not.toContain('制作人')
    await choose(['expectedRange'])
    await setValue('expectedRange', ['2026-09-28T12:00:00', '2026-09-28T10:00:00'])
    await reason()
    await click('下一步：核对修改')
    expect(stage()).toBe(0)
    await click('重置')
    expect(stage()).toBe(0)
    expect(wrapper.getComponent(ElCheckboxGroup).props('modelValue')).toEqual([])
  })
  it('调整制作人可直接保存，不要求额外确认重叠', async () => {
    await open()
    await choose(['assigneeUserId'])
    await setValue('assigneeUserId', 8)
    await reason(); await click('下一步：核对修改'); await click('应用到 2 个镜头')
    expect(adjustShotProduction).toHaveBeenCalledTimes(1)
    expect(adjustShotProduction.mock.calls[0][1]).not.toHaveProperty('overlapAcknowledged')
    expect(document.body.textContent).not.toContain('已核对，仍按此安排保存')
    expect(wrapper.emitted('close')).toEqual([[{ saved: true }]])
  })
  it.each([409, 0])('冲突或未知提交结果 %s 禁止直接重发', async status => {
    adjustShotProduction.mockRejectedValue({ httpStatus: status, message: '任务已变化' })
    await open(); await choose(['priority']); await reason(); await click('下一步：核对修改'); await click('应用到 2 个镜头')
    expect(adjustShotProduction).toHaveBeenCalledTimes(1)
    expect(button('应用到 2 个镜头')).toBeUndefined()
    expect(document.body.textContent).toContain(status ? '本批未保存' : '提交结果未知')
  })
  it('单条入口共用流程，双锁号不一致时阻止填写', async () => {
    getShotDetail.mockResolvedValue({ data: { lockVersion: 9, task: { taskId: 11, lockVersion: 3 }, allowedActions: ['task.adjust'] } })
    await open({ shots: [shots[0]] })
    expect(document.body.textContent).toContain('编辑制作任务 · ')
    expect(document.body.textContent).toContain('制作信息已变化')
    expect(button('下一步：核对修改')).toBeUndefined()
  })
  it('加载中卸载取消读取，不能继续其他镜头', async () => {
    let complete
    getShotDetail.mockImplementation(() => new Promise(resolve => { complete = resolve }))
    await open(); wrapper.unmount(); wrapper = null
    expect(getShotDetail.mock.calls[0][2].signal.aborted).toBe(true)
    complete({ data: {} }); await flushPromises()
    expect(getShotDetail).toHaveBeenCalledTimes(1)
    expect(adjustShotProduction).not.toHaveBeenCalled()
  })
})
