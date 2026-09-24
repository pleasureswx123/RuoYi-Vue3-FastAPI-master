import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import CandidateGenerationPrompt from '@/components/version/CandidateGenerationPrompt.vue'
import { updateCandidateGenerationPrompt } from '@/api/shot-grid/versions'

vi.mock('@/api/shot-grid/versions', () => ({ updateCandidateGenerationPrompt: vi.fn() }))
const candidate = { candidateId: 9, candidateNumber: 'V001_01', generationPrompt: null }
function create(editable = true) {
  return mount(CandidateGenerationPrompt, {
    props: { candidate, version: { versionId: 7, canEditGenerationPrompt: editable } }
  })
}
const button = (wrapper, text) => wrapper.findAll('button').find(item => item.text() === text)
describe('后补提示词', () => {
  it('权限、取消重置、校验及保存使用当前文件和原值', async () => {
    const readonly = create(false)
    expect(readonly.find('button').exists()).toBe(false)
    readonly.unmount()
    const wrapper = create()
    await button(wrapper, '补充提示词').trigger('click')
    await wrapper.find('textarea').setValue('未保存')
    await button(wrapper, '取消').trigger('click')
    await button(wrapper, '补充提示词').trigger('click')
    expect(wrapper.find('textarea').element.value).toBe('')
    await wrapper.find('textarea').setValue('非法\u0001')
    await button(wrapper, '保存提示词').trigger('click')
    await flushPromises()
    expect(updateCandidateGenerationPrompt).not.toHaveBeenCalled()
    const updated = { versionId: 7, candidates: [{ ...candidate, generationPrompt: '镜头\n推进' }] }
    updateCandidateGenerationPrompt.mockResolvedValueOnce({ data: updated })
    await wrapper.find('textarea').setValue('镜头\n推进')
    await button(wrapper, '保存提示词').trigger('click')
    await flushPromises()
    expect(updateCandidateGenerationPrompt).toHaveBeenCalledWith(7, 9, {
      generationPrompt: '镜头\n推进', previousGenerationPrompt: null
    })
    expect(wrapper.emitted('saved')[0]).toEqual([updated])
    wrapper.unmount()
  })
  it('失败保留输入，切换候选隔离迟到响应', async () => {
    const wrapper = create()
    await button(wrapper, '补充提示词').trigger('click')
    await wrapper.find('textarea').setValue('保留输入')
    updateCandidateGenerationPrompt.mockRejectedValueOnce(new Error('提示词已被修改'))
    await button(wrapper, '保存提示词').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('提示词已被修改')
    expect(wrapper.find('textarea').element.value).toBe('保留输入')
    let finish
    updateCandidateGenerationPrompt.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await button(wrapper, '保存提示词').trigger('click')
    await flushPromises()
    expect(button(wrapper, '取消').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ candidate: { ...candidate, candidateId: 10 } })
    finish({ data: { versionId: 7 } })
    await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined()
    expect(wrapper.find('textarea').exists()).toBe(false)
    wrapper.unmount()
  })
})
