import { onBeforeUnmount, ref, watch } from 'vue'
import { requestMedia } from '@/utils/request'
import { createObjectUrlOwner } from './objectUrl'

export function useProtectedMedia(source, { range } = {}) {
  const objectUrl = ref(''), loading = ref(false), error = ref('')
  const owner = createObjectUrlOwner()
  let controller

  async function load(value) {
    controller?.abort()
    controller = new AbortController()
    owner.release()
    objectUrl.value = ''
    error.value = ''
    if (!value?.url) return
    loading.value = true
    try {
      const blob = await requestMedia(value.url, { range, projectId: value.projectId, signal: controller.signal })
      if (!controller.signal.aborted) objectUrl.value = owner.replace(blob)
    } catch (reason) {
      if (reason?.name !== 'CanceledError' && reason?.code !== 'ERR_CANCELED') {
        error.value = reason?.status === 416 ? '媒体分段请求失败（Range 416），请重新加载或下载原文件。' : '媒体加载失败，请检查权限或网络后重试。'
      }
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }

  watch(source, load, { immediate: true })
  onBeforeUnmount(() => { controller?.abort(); owner.release() })
  return { objectUrl, loading, error, reload: () => load(source.value) }
}
