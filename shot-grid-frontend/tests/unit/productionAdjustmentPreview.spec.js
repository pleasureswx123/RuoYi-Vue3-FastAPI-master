import { mount } from '@vue/test-utils'
import { ElButton, ElCheckbox, ElCollapse } from 'element-plus'
import { describe, expect, it } from 'vitest'
import Preview from '@/views/shot/components/ProductionAdjustmentPreview.vue'
const field = (key, changed) => ({ key, label: key, before: '原值', after: '新值', changed })
const shots = [1, 2].map(key => ({ key, label: `EP001 / 001 / 000${key}`, fields: [field('制作内容', true), field('优先级', false)] }))
describe('制作任务核对卡片', () => {
  it('批量默认全部收起并隐藏未变化字段，可全部展开与收起', async () => {
    const wrapper = mount(Preview, { props: { shots, common: true } })
    expect(wrapper.getComponent(ElCollapse).props('modelValue')).toEqual([])
    expect(wrapper.findAll('.review-field')).toHaveLength(2)
    for (const item of wrapper.findAll('.review-field')) {
      expect(item.text()).toContain('修改前')
      expect(item.text()).toContain('修改后')
      expect(item.text()).toContain('原值')
      expect(item.text()).toContain('新值')
    }
    await wrapper.getComponent(ElCheckbox).setValue(true)
    expect(wrapper.findAll('.review-field')).toHaveLength(4)
    await wrapper.findAllComponents(ElButton).find(item => item.text() === '全部展开').trigger('click')
    expect(wrapper.getComponent(ElCollapse).props('modelValue')).toEqual([1, 2])
    await wrapper.findAllComponents(ElButton).find(item => item.text() === '全部收起').trigger('click')
    expect(wrapper.getComponent(ElCollapse).props('modelValue')).toEqual([])
    wrapper.unmount()
  })
  it('参考内容显示空原值及追加后的完整说明和附件', () => {
    const oldFile = { fileId: 'old', originalName: '已有.png' }
    const newFile = { localId: 'new', originalName: '新增.png' }
    const reference = { key: 'refs', label: '参考内容', isReference: true, changed: true, beforeDescription: '', beforeFiles: [] }
    const wrapper = mount(Preview, {
      props: { shots: [{ key: 1, label: '镜头1', fields: [reference] }, { key: 2, label: '镜头2', fields: [{ ...reference, beforeDescription: '已有说明', beforeFiles: [oldFile] }] }], common: true, addedDescription: '新增说明', addedFiles: [newFile] },
      global: { stubs: { ReviewReferenceInput: { props: ['files'], template: '<div class="test-files">{{ files.map(file => file.originalName).join("、") }}</div>' } } }
    })
    const fields = wrapper.findAll('.review-field')
    expect(fields[0].text()).toContain('暂无参考内容')
    expect(fields[0].find('.review-new').text()).toContain('新增说明')
    expect(fields[0].find('.review-new').text()).toContain('新增.png')
    expect(fields[1].find('.review-new').text()).toContain('已有说明')
    expect(fields[1].find('.review-new').text()).toContain('新增说明')
    expect(fields[1].find('.review-new').text()).toContain('已有.png、新增.png')
    wrapper.unmount()
  })
  it('单镜头直接展示前后值，清空明确标注', () => {
    const wrapper = mount(Preview, { props: { shots: [{ ...shots[0], fields: [{ ...field('制作内容', true), after: '（清空）' }] }] } })
    expect(wrapper.text()).toContain('修改前')
    expect(wrapper.text()).toContain('修改后')
    expect(wrapper.text()).toContain('将清空')
    expect(wrapper.text()).not.toContain('全部收起')
    wrapper.unmount()
  })
})
