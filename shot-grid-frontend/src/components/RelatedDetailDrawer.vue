<script setup>
import { computed, defineAsyncComponent, ref } from 'vue'
import { ElDrawer } from 'element-plus'
import 'element-plus/es/components/drawer/style/css'
import { detailResource } from '@/composables/useDetailNavigation'
import { useSessionStore } from '@/store/modules/session'

defineProps({ returnLabel: { type: String, default: '镜头详情' } })

const session = useSessionStore()
const visible = ref(false)
const entries = ref([])
const current = computed(() => entries.value.at(-1))
const definitions = {
  version: { title: '版本详情', permission: 'shotgrid:version:query', prop: 'targetVersionId', component: defineAsyncComponent(() => import('@/views/version/VersionDetailView.vue').then(module => module.default)) },
  review: { title: '审核详情', permission: 'shotgrid:reviewList:query', prop: 'targetReviewListId', component: defineAsyncComponent(() => import('@/views/review/ReviewDetailView.vue').then(module => module.default)) },
  task: { title: '任务详情', permission: 'shotgrid:task:query', prop: 'targetTaskId', component: defineAsyncComponent(() => import('@/views/task/TaskDetailView.vue').then(module => module.default)) }
}
const definition = computed(() => definitions[current.value?.type])
const allowed = computed(() => session.permissions.includes('*:*:*') || session.permissions.includes(definition.value?.permission))
function open(target) {
  const resource = detailResource(target)
  if (!resource) return false
  if (!visible.value) entries.value = []
  if (current.value?.type !== resource.type || current.value?.id !== resource.id) entries.value.push(resource)
  visible.value = true
  return true
}
function reset() {
  if (!visible.value) entries.value = []
}
defineExpose({ open })
</script>

<template>
  <el-drawer v-model="visible" class="sg-detail-drawer related-detail-drawer" modal-class="sg-detail-drawer-mask" header-class="sg-detail-drawer__header" body-class="sg-detail-drawer__body" :title="definition?.title || '关联详情'" size="80%" append-to-body destroy-on-close :close-on-click-modal="false" @closed="reset">
    <template #header>
      <div class="related-detail-heading"><strong>{{ definition?.title }}</strong><el-button v-if="entries.length > 1" link type="primary" @click="entries.pop()">返回上一层详情</el-button><small>关闭返回{{ returnLabel }}</small></div>
    </template>
    <template v-if="visible && current">
      <component :is="definition.component" v-if="allowed" :key="`${current.type}:${current.id}`" v-bind="{ [definition.prop]: current.id }" embedded />
      <el-alert v-else title="当前账号没有此详情的查看权限" type="error" :closable="false" show-icon />
    </template>
  </el-drawer>
</template>

<style>
.related-detail-drawer { max-width: none; }
.related-detail-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; }
.related-detail-heading small { color: var(--sg-text-muted); }
</style>
