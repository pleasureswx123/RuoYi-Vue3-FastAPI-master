<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, provide, ref } from 'vue'
import { ElDrawer } from 'element-plus'
import 'element-plus/es/components/drawer/style/css'
import { detailNavigationKey, detailResource } from '@/composables/useDetailNavigation'
import { useSessionStore } from '@/store/modules/session'

const session = useSessionStore()
const emit = defineEmits(['closed'])
provide(detailNavigationKey, target => open(target))
const visible = ref(false)
const detailView = ref(null)
let navigating = false
let disposed = false
onBeforeUnmount(() => { disposed = true })
const entries = ref([])
const current = computed(() => entries.value.at(-1))
const definitions = {
  version: { title: '版本详情', permission: 'shotgrid:version:query', prop: 'targetVersionId', component: defineAsyncComponent(() => import('@/views/version/VersionDetailView.vue').then(module => module.default)) },
  review: { title: '审核详情', permission: 'shotgrid:reviewList:query', prop: 'targetReviewListId', component: defineAsyncComponent(() => import('@/views/review/ReviewDetailView.vue').then(module => module.default)) },
  task: { title: '任务详情', permission: 'shotgrid:task:query', prop: 'targetTaskId', component: defineAsyncComponent(() => import('@/views/task/TaskDetailView.vue').then(module => module.default)) }
}
const definition = computed(() => definitions[current.value?.type])
const allowed = computed(() => session.permissions.includes('*:*:*') || session.permissions.includes(definition.value?.permission))
function open(target, options = {}) {
  const resource = detailResource(target)
  if (!resource) return false
  if (resource.type === 'task') resource.initialSection = ['submit', 'feedback', 'reference'].includes(options.section) ? options.section : 'brief'
  if (visible.value && current.value?.type === resource.type && current.value?.id === resource.id) {
    if (resource.type === 'task') current.value.initialSection = resource.initialSection
    return true
  }
  const apply = () => {
    if (!visible.value) entries.value = []
    if (current.value?.type !== resource.type || current.value?.id !== resource.id) entries.value.push(resource)
    visible.value = true
  }
  if (visible.value && detailView.value?.canLeave) void guardedNavigation(apply)
  else apply()
  return true
}
async function guardedNavigation(action) {
  if (navigating) return
  navigating = true
  try { if ((await detailView.value?.canLeave?.()) !== false && !disposed) action() }
  finally { navigating = false }
}
function beforeClose(done) { void guardedNavigation(done) }
function reset() {
  if (!visible.value) {
    entries.value = []
    emit('closed')
  }
}
defineExpose({ open })
</script>

<template>
  <el-drawer v-model="visible" class="sg-detail-drawer related-detail-drawer" modal-class="sg-detail-drawer-mask" header-class="sg-detail-drawer__header" body-class="sg-detail-drawer__body" :title="definition?.title || '关联详情'" :size="session.isCreatorWorkspace && current?.type === 'task' ? 'min(760px, 94vw)' : '80%'" append-to-body destroy-on-close :close-on-click-modal="false" :before-close="beforeClose" @closed="reset">
    <template #header>
      <div class="related-detail-heading"><strong>{{ definition?.title }}</strong><el-button v-if="entries.length > 1" link type="primary" @click="guardedNavigation(() => entries.pop())">返回上一层详情</el-button></div>
    </template>
    <template v-if="visible && current">
      <component :is="definition.component" v-if="allowed" ref="detailView" :key="`${current.type}:${current.id}`" v-bind="{ [definition.prop]: current.id, ...(current.type === 'task' ? { initialSection: current.initialSection } : {}) }" embedded @completed="visible = false" />
      <el-alert v-else title="当前账号没有此详情的查看权限" type="error" :closable="false" show-icon />
    </template>
  </el-drawer>
</template>

<style>
.related-detail-drawer { max-width: none; }
.related-detail-drawer > .sg-detail-drawer__body:has(> .review-detail-page--embedded, > .task-detail-page--embedded) { padding: 12px; }
.related-detail-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; }
</style>
