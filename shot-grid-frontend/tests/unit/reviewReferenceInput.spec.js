import { defineComponent } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReviewReferenceInput from '@/components/review/ReviewReferenceInput.vue'
import { useReviewReferenceAttachments } from '@/composables/useReviewReferenceAttachments'

vi.mock('@/api/shot-grid/reviews', () => ({ uploadReviewReferenceFile: vi.fn() }))
let wrapper
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals() })
const host = defineComponent({
  components: { ReviewReferenceInput },
  setup: () => useReviewReferenceAttachments(),
  template: '<ReviewReferenceInput :files="referenceAttachments" @add="addReferenceFile" @remove="removeReferenceFile" />'
})
async function select(files) {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')
  await flushPromises()
}
describe('审核参考内容输入', () => {
  it('限制类型、重复、单个大小及批量选择数量，20 MiB 边界可选', async () => {
    wrapper = mount(host)
    const tooLarge = new File(['a'], '过大.mov')
    Object.defineProperty(tooLarge, 'size', { value: 20 * 1024 * 1024 + 1 })
    const boundary = new File(['b'], '边界.mov')
    Object.defineProperty(boundary, 'size', { value: 20 * 1024 * 1024 })
    await select([new File(['x'], '危险.exe'), new File(['x'], 'pdf'), tooLarge])
    expect(wrapper.getComponent(ReviewReferenceInput).props('files')).toHaveLength(0)
    await select([boundary, new File(['b'], '参考.pdf'), new File(['b'], '参考.pdf'), ...[1, 2, 3, 4].map(i => new File(['x'], `${i}.txt`))])
    const files = wrapper.getComponent(ReviewReferenceInput).props('files')
    expect(files).toHaveLength(5)
    expect(files[0].originalName).toBe('边界.mov')
    expect(wrapper.get('input[type="file"]').element.disabled).toBe(true)
    await wrapper.get('button[aria-label="移除参考文件 参考.pdf"]').trigger('click')
    expect(wrapper.getComponent(ReviewReferenceInput).props('files')).toHaveLength(4)
    expect(wrapper.get('input[type="file"]').element.disabled).toBe(false)
  })
  it('移除和卸载释放图片预览', async () => {
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:reference'), revokeObjectURL })
    wrapper = mount(host)
    await select([new File(['x'], '参考.png')])
    expect(wrapper.find('img').attributes('src')).toBe('blob:reference')
    await wrapper.get('button[aria-label="移除参考文件 参考.png"]').trigger('click')
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
    await select([new File(['y'], '另一张.png')])
    wrapper.unmount()
    wrapper = null
    expect(revokeObjectURL).toHaveBeenCalledTimes(2)
  })
})
