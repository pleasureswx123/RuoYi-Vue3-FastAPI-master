import { mount } from '@vue/test-utils'
import { ElAlert, ElDescriptions, ElDescriptionsItem } from 'element-plus'
import { expect, it } from 'vitest'
import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'

it('空内容不阻止开工，更新内容后立即展示最新信息并移除提醒', async () => {
  const wrapper = mount(ShotProductionInfo, {
    props: { shot: { description: '   ' } },
    global: { components: { ElAlert, ElDescriptions, ElDescriptionsItem }, stubs: { ReviewReferenceFiles: true } }
  })
  try {
    expect(wrapper.findComponent(ElAlert).text()).toContain('分配制作人、排期和确认开工')
    await wrapper.setProps({ shot: { description: '补齐后的制作要求' } })
    expect(wrapper.findComponent(ElAlert).exists()).toBe(false)
    expect(wrapper.text()).toContain('补齐后的制作要求')
  } finally { wrapper.unmount() }
})
