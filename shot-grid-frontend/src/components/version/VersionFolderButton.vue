<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'
import { getTaskDetail } from '@/api/shot-grid/tasks'
import { useSessionStore } from '@/store/modules/session'
import { candidateFolderPath, requestLocalDemoFolder } from '@/utils/folderOpener'

const props = defineProps({ version: { type: Object, required: true }, file: { type: Object, required: true }, canDownload: Boolean })
const session = useSessionStore()
const local = import.meta.env.DEV && ['127.0.0.1', 'localhost', '[::1]'].includes(window.location.hostname)
const preview = ref(false)
const busy = ref(false)
let controller
watch(() => [props.version.versionId, props.file.fileId, props.canDownload, session.permissions.join('|')], () => { controller?.abort(); busy.value = false; preview.value = false })
onBeforeUnmount(() => controller?.abort())
async function open() {
  if (!props.canDownload || busy.value) return
  if (!local) { preview.value = true; return }
  if (!session.permissions.some(permission => ['*:*:*', 'shotgrid:task:query'].includes(permission))) {
    ElMessage.warning('当前账号没有任务详情权限'); return
  }
  const request = new AbortController(); controller = request; busy.value = true
  const version = props.version, file = props.file
  try {
    const { data: task } = await getTaskDetail(version.taskId, { signal: request.signal })
    if (request.signal.aborted) return
    if (Number(task.taskId) !== Number(version.taskId) || Number(task.project?.projectId) !== Number(version.projectId)) throw new Error('文件与任务归属不匹配，请刷新')
    const target = task.target
    const asset = target?.targetType === 'asset_item'
    if (!asset && target?.targetType !== 'shot') throw new Error('制作目标不可用')
    const opened = requestLocalDemoFolder(Number(version.projectId), Number(asset ? target.assetItemId ?? target.targetId : target.shotId ?? target.targetId), Number(version.versionId), Number(file.candidateId || 0), asset ? Number(target.assetId) : 0, ...(file.folderRelativePath ? [file.folderRelativePath] : []))
    if (!opened) throw new Error('制作目标编号无效，请刷新')
    ElMessage.info('已请求打开本地模拟文件夹，内容为演示副本，不是正式成果。')
  } catch (error) { if (!request.signal.aborted) ElMessage.warning(error.message || '打开失败，请重试') }
  finally { if (controller === request) busy.value = false }
}
</script>

<template>
  <el-button v-if="file.role === 'review_media'" size="small" :icon="FolderOpened" :title="file.folderRelativePath || '打开当前版本文件夹'" :loading="busy" :disabled="!canDownload" @click="open">打开所在文件夹（{{ local ? '本地模拟' : '演示' }}）</el-button>
  <el-dialog v-model="preview" title="文件夹位置预览（演示）" width="min(520px, 92vw)" append-to-body destroy-on-close>
    <el-alert title="当前仅演示入口，不会打开文件夹或连接 NAS。" type="info" :closable="false" />
    <p>{{ candidateFolderPath([file]) || '尚未提供可用的原文件位置' }}</p>
    <template #footer><el-button @click="preview = false">关闭预览</el-button></template>
  </el-dialog>
</template>
