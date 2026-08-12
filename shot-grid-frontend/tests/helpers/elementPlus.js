export async function setElSelectValue(wrapper, value) {
  wrapper.vm.$emit('update:modelValue', value)
  wrapper.vm.$emit('change', value)
  await wrapper.vm.$nextTick()
}
