import { mount } from '@vue/test-utils'
import { ElDatePicker, ElMessage } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleDateRangePicker from '@/components/ScheduleDateRangePicker.vue'

vi.mock('element-plus', async importOriginal => ({ ...await importOriginal(), ElMessage: { warning: vi.fn() } }))
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-09-30T10:30:00')) })
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })
describe('排期开始时间限制', () => {
  it('禁用历史日期，今天和未来可选', () => {
    const wrapper = mount(ScheduleDateRangePicker)
    const disabled = wrapper.findComponent(ElDatePicker).props('disabledDate')
    expect(disabled(new Date('2026-09-29T23:59:59'))).toBe(true)
    expect(disabled(new Date('2026-09-30T00:00:00'))).toBe(false)
    expect(disabled(new Date('2026-10-01T00:00:00'))).toBe(false)
    wrapper.unmount()
  })
  it('回显历史排期不清空，新输入过去时刻则拒绝', async () => {
    const wrapper = mount(ScheduleDateRangePicker, { props: { modelValue: ['2026-09-29T10:00:00', '2026-10-01T18:00:00'] } })
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', ['2026-09-30T10:29:59', '2026-10-01T18:00:00'])
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual([[]])
    expect(ElMessage.warning).toHaveBeenCalled()
    wrapper.unmount()
  })
  it('未来时间可选，停留后再次选择按实时当前时间检查', () => {
    const wrapper = mount(ScheduleDateRangePicker)
    const range = ['2026-09-30T10:31:00', '2026-10-01T18:00:00']
    wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', range)
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual([range])
    vi.setSystemTime(new Date('2026-09-30T10:32:00'))
    wrapper.findComponent(ElDatePicker).vm.$emit('update:modelValue', range)
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual([[]])
    wrapper.unmount()
  })
})
