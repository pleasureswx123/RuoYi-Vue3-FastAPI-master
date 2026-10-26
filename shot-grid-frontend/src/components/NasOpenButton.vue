<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { FolderOpened } from '@element-plus/icons-vue'
import { useSessionStore } from '@/store/modules/session'
import NasFolderMenu from './NasFolderMenu.vue'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  taskId: { type: [Number, String], default: 0 },
  versionId: { type: [Number, String], default: 0 },
  fileId: { type: String, default: '' },
  kind: { type: String, default: 'version' },
  text: Boolean,
  size: { type: String, default: 'small' },
  disabled: Boolean
})
const session = useSessionStore()
const allowed = computed(() => session.permissions.includes('*:*:*') || session.permissions.includes(props.kind === 'project' ? 'shotgrid:storage:path' : 'shotgrid:version:query'))
const activated = ref(false)
const busy = ref(false)
const opener = ref(null)
// 每行只渲染按钮，使用时才挂载目录选择和安装帮助。
watch(() => [props.projectId, props.taskId, props.versionId, props.fileId, allowed.value], () => { activated.value = false; busy.value = false })
async function open() {
  if (busy.value || props.disabled || !allowed.value) return
  busy.value = true
  activated.value = true
  try {
    await nextTick()
    await opener.value?.openTarget({ kind: props.kind, taskId: props.taskId, versionId: props.versionId, fileId: props.fileId })
  } finally { busy.value = false }
}
</script>

<template>
  <el-button v-if="allowed" :size="size" :text="text" :icon="FolderOpened" :loading="busy" :disabled="disabled" @click="open">在文件资源管理器中打开</el-button>
  <NasFolderMenu v-if="activated && allowed" ref="opener" :project-id="Number(projectId)" :can-query="allowed" />
</template>
