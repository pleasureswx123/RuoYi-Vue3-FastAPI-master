import { ElButton, ElCheckbox, ElDatePicker, ElSelect } from 'element-plus'
import { flushPromises } from '@vue/test-utils'

export const expectedTaskTimes = { priority: 'normal', expectedStartTime: '2099-09-01T09:00:00', expectedEndTime: '2099-09-02T18:00:00' }

export async function completeTaskStartForm(wrapper, action = 'confirm') {
  await flushPromises()
  const dialog = wrapper.findComponent({ name: 'TaskStartDialog' })
  if (action === 'confirm') {
    await setElSelectValue(dialog.findComponent(ElSelect), 'normal')
    dialog.findComponent(ElDatePicker).vm.$emit('update:modelValue', [expectedTaskTimes.expectedStartTime, expectedTaskTimes.expectedEndTime])
    await dialog.findComponent(ElCheckbox).find('input').setValue(true)
    await flushPromises()
  }
  await dialog.findAllComponents(ElButton).find(button => buttonLabel(button) === (action === 'confirm' ? '确认开工' : '暂不开工')).trigger('click')
  await flushPromises()
}

export function buttonLabel(wrapper) {
  return wrapper.attributes('aria-label') || wrapper.text()
}

export async function setElSelectValue(wrapper, value) {
  wrapper.vm.$emit('update:modelValue', value)
  wrapper.vm.$emit('change', value)
  await wrapper.vm.$nextTick()
}
