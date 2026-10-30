import { mount } from '@vue/test-utils'
import { ElAlert, ElDescriptions, ElDescriptionsItem } from 'element-plus'
import { expect, it } from 'vitest'
import ShotProductionInfo from '@/views/shot/components/ShotProductionInfo.vue'

it('空内容提醒开工前补齐，更新内容后立即展示最新信息并移除提醒', async () => {
  const wrapper = mount(ShotProductionInfo, {
    props: { shot: { description: '   ' } },
    global: { components: { ElAlert, ElDescriptions, ElDescriptionsItem }, stubs: { ReviewReferenceFiles: true } }
  })
  try {
    expect(wrapper.findComponent(ElAlert).text()).toContain('可先分配制作人和排期')
    await wrapper.setProps({ shot: { description: '补齐后的制作要求' } })
    expect(wrapper.findComponent(ElAlert).exists()).toBe(false)
    expect(wrapper.text()).toContain('补齐后的制作要求')
  } finally { wrapper.unmount() }
})
