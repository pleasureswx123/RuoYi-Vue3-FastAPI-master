<script setup>
import ResultsDrawer from '@/components/ResultsDrawer.vue'
import NasFolderMenu from '@/components/NasFolderMenu.vue'

import FinalVersionTag from '@/components/version/FinalVersionTag.vue'
import 'element-plus/es/components/popover/style/css'
import 'element-plus/es/components/checkbox-group/style/css'
import 'element-plus/es/components/slider/style/css'
import TaskFeedbackShortcut from '@/views/task/components/TaskFeedbackShortcut.vue'
import ForceDeleteAction from '@/components/ForceDeleteAction.vue'
import TargetPurgeStatus from '@/components/TargetPurgeStatus.vue'
import { myProjectRoles, memberRoles } from '@/views/project/projectPresentation'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import ShotTaskFeedbackDialog from '@/components/version/ShotTaskFeedbackDialog.vue'
import ProductionAdjustmentDialog from './components/ProductionAdjustmentDialog.vue'
import { shotFeatures } from './shotFeatures'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLeaveProtection } from '@/composables/useLeaveProtection'
import { ElCheckbox, ElCheckboxGroup, ElDatePicker, ElPopover, ElSlider, ElMessage, ElMessageBox } from 'element-plus'
import { shotDetailColumns, useShotTablePresentation } from './useShotTablePresentation'
import { Calendar, Clock, Delete, Edit, Filter, List, Plus, Refresh, RefreshLeft, Search, Switch, Upload, User, VideoCamera, VideoPlay, View } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'

import { getProjectDetail } from '@/api/shot-grid/projects'
import { useTaskStartDialog } from '@/views/task/useTaskStartDialog'
import TaskStartDialog from '@/views/task/components/TaskStartDialog.vue'
import BatchShotStartDialog from './components/BatchShotStartDialog.vue'
import { batchAssignShotTasks, batchDeleteShots, getEpisodePage, getScenePage, getShotDetail, getShotPage, listShotAssignees, reorderShot } from '@/api/shot-grid/shots'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { useTaskStatePolling } from '@/composables/useTaskStatePolling'
import { useCurrentTime } from '@/composables/useCurrentTime'
import { useVersionCollectionRealtime } from '@/composables/useVersionCollectionRealtime'
import { formatTaskDateTime, taskTimeReminder } from '@/views/task/taskPresentation'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import ShotActionButtons from './components/ShotActionButtons.vue'
import RelatedDetailDrawer from '@/components/RelatedDetailDrawer.vue'
import { getVersionDetail } from '@/api/shot-grid/versions'
import { projectRoleMeta, storageMeta } from '@/views/project/projectPresentation'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'
import EpisodeSceneCreateDialog from '@/views/shot/components/EpisodeSceneCreateDialog.vue'
import ShotDetailView from '@/views/shot/ShotDetailView.vue'
import ShotFormDialog from '@/views/shot/components/ShotFormDialog.vue'
import ShotAssignDialog from '@/views/shot/components/ShotAssignDialog.vue'
import ShotImportDialog from '@/views/shot/components/ShotImportDialog.vue'
import { formatShotCode, formatShotDuration, shotAssigneeName, shotAssigneeOptionLabel, shotErrorState, shotStatusMeta, shotStatusTagClass } from '@/views/shot/shotPresentation'

const rowHeightForm = ref(null)
const purgeRefresh = ref(0)

const ScheduleBoard = defineAsyncComponent(() => import('@/views/schedule/ScheduleBoard.vue'))
const ShotResultsPanel = defineAsyncComponent(() => import('./components/ShotResultsPanel.vue'))

const nasFolderMenu = ref(null)
const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const project = ref(null)
const episodes = ref([])
const scenes = ref([])
const members = ref([])
const shots = ref([])
const storyboardSize = ref('medium')
const collapsedScenes = ref([])
const storyboardGroups = computed(() => {
  const groups = new Map()
  for (const shot of shots.value) {
    const key = `${shot.episodeId || shot.episodeCode}:${shot.sceneId || shot.sceneCode}`
    if (!groups.has(key)) groups.set(key, { key, label: `${shot.episodeCode} / ${shot.sceneCode} ${shot.sceneName || ''}`, shots: [] })
    groups.get(key).shots.push(shot)
  }
  return [...groups.values()]
})
const expandedScenes = computed({
  get: () => storyboardGroups.value.map(group => group.key).filter(key => !collapsedScenes.value.includes(key)),
  set: keys => { collapsedScenes.value = storyboardGroups.value.map(group => group.key).filter(key => !keys.includes(key)) }
})
const storyboardSelection = computed({
  get: () => [...selectedShotIds.value],
  set: ids => { if (!batchBusy.value) selectedShotIds.value = new Set(shots.value.filter(shot => ids.includes(Number(shot.shotId)) && canSelectShot(shot)).map(shot => Number(shot.shotId))) }
})
async function openScheduleResults(task) {
  if (Number(task.projectId) !== currentProjectId.value || task.target?.targetKind !== 'shot') return false
  await openShotResults({ shotId: Number(task.target.targetId) })
  return resultsShotId.value === Number(task.target.targetId)
}
const directFeedbackDialog = ref(null)
const directFeedbackOpen = ref(false)
const selectedShotIds = ref(new Set())
const total = ref(0)
const hasNext = ref(false)
const projectsLoading = ref(false)
const shotsLoading = ref(false)
const scenesLoading = ref(false)
const projectsError = ref(null)
const shotsError = ref(null)
const viewMode = ref('table')
const scheduleBrowseState = ref(null)
useLeaveProtection(() => resultsPanel.value?.canLeave?.() ?? true, () => Boolean(resultsPanel.value?.dirty))
async function changeViewMode(mode) {
  if (mode === viewMode.value || (resultsPanel.value && !await resultsPanel.value.canLeave())) return
  viewMode.value = mode
}
const showDetail = ref(false)
const workDrawer = ref(null)
const openingWorkShotId = ref(null)
const workDrawerProjectId = ref(null)
function canViewTask(shot) {
  return hasPermission('shotgrid:task:query') && Number.isSafeInteger(Number(shot.taskId)) && Number(shot.taskId) > 0
}
function openTaskDetail(shot) {
  if (!canViewTask(shot) || !currentProjectId.value) return
  workDrawerProjectId.value = currentProjectId.value
  workDrawer.value?.open(`/tasks/${Number(shot.taskId)}`)
}
// 表格与卡片共用操作定义，权限、加载状态和入口保持一致。
function shotActions(shot) {
  const work = workAction(shot)
  const assigned = Boolean(shot.task || shot.taskLockVersion != null)
  const items = []
  const add = (key, visible, button, run) => { if (visible) items.push({ key, button, run }) }
  const workButton = work && {
    label: work.label, type: work.supplemental ? 'info' : work.tone, color: work.color,
    plain: Boolean(work.supplemental), icon: work.supplemental ? work.icon : VideoPlay,
    hint: work.hint, title: work.hint,
    loading: openingWorkShotId.value === shot.shotId, disabled: Boolean(openingWorkShotId.value)
  }
  add('start', canStartShot(shot), {
    label: '确认开工', type: 'success', plain: false, icon: VideoPlay,
    loading: startingOperation.value?.shotId === shot.shotId, disabled: startDisabled.value
  }, () => confirmStartShot(shot))
  add('feedback', canDirectFeedback(shot), { label: '添加反馈', type: 'warning', plain: false, icon: Edit, disabled: startDisabled.value || directFeedbackOpen.value }, () => openDirectFeedback([shot]))
  add('edit', canEditShot(shot), {
    label: '编辑', title: '编辑镜头', type: 'warning', plain: false, icon: Edit, loading: editingShotId.value === Number(shot.shotId), disabled: deleting.value
  }, () => openEditDialog(shot))
  const hasSchedule = Boolean((shot.expectedStartTime || shot.task?.expectedStartTime) && (shot.expectedEndTime || shot.task?.expectedEndTime))
  add('schedule', canScheduleShot(shot), {
    label: hasSchedule ? '调整排期' : '设置排期', type: 'primary', plain: false, icon: Clock, disabled: startDisabled.value
  }, () => openBatchStart('schedule', [shot], true))
  add('work', work && !work.supplemental, workButton, () => openWork(shot))
  add('assign', canOpenShotAssign(shot), {
    label: assigned ? '改派制作人' : '分配制作人', type: assigned ? 'warning' : 'primary', plain: assigned,
    icon: assigned ? Switch : User, loading: assigningShotId.value === Number(shot.shotId),
    disabled: shotsLoading.value || assigning.value || deleting.value || Boolean(startingOperation.value) || Boolean(singleAssignContext.value) || Boolean(assigningShotId.value)
  }, () => openSingleAssign(shot))
  add('view', canViewTask(shot), { label: '查看任务', type: 'primary', icon: View }, () => openTaskDetail(shot))
  add('history', true, { label: '制作履历', color: '#159b94', icon: Clock }, () => openShot(shot))
  add('adjust', canAdjustShot(shot), { label: '编辑', type: 'warning', icon: Edit, disabled: startDisabled.value }, () => openProductionAdjustment([shot]))
  add('supplement', work?.supplemental, workButton, () => openWork(shot))
  add('delete', canDelete.value, {
    label: '删除', hint: canDeleteShot(shot) ? '删除镜头' : '任务已经开始，不能删除',
    type: 'danger', icon: Delete, disabled: !canDeleteShot(shot) || deleting.value
  }, () => confirmDeleteShots([shot]))
  // 按当前制作阶段突出下一步操作，其余按钮保持原顺序。
  const primaryKey = shot.status === 'unassigned' ? 'assign' : 'work'
  const primaryIndex = items.findIndex(item => item.key === primaryKey)
  if (primaryIndex > 0) items.unshift(...items.splice(primaryIndex, 1))
  if (['unassigned', 'pending_schedule', 'not_started'].includes(shot.status)) {
    const editIndex = items.findIndex(item => item.key === 'edit')
    if (editIndex >= 0) {
      const [editAction] = items.splice(editIndex, 1)
      const deleteIndex = items.findIndex(item => item.key === 'delete')
      items.splice(deleteIndex >= 0 ? deleteIndex : items.length, 0, editAction)
    }
  }
  return items
}
async function loadScheduleActionTarget(task, options) {
  const projectId = currentProjectId.value
  if (Number(task.projectId) !== Number(projectId) || task.target?.targetKind !== 'shot') return null
  if (!hasPermission('shotgrid:shot:query')) {
    return { taskId: task.taskId, allowedActions: [], scheduleViewOnly: true }
  }
  const response = await getShotDetail(projectId, task.target.targetId, options)
  const shot = response.data
  if (Number(shot?.taskId ?? shot?.task?.taskId) !== Number(task.taskId) || Number(shot?.projectId) !== Number(projectId)) {
    throw new Error('任务与镜头信息已变化，请刷新排期后重试')
  }
  return shot
}
function scheduleTaskActions(shot) {
  if (!shot) return []
  const keys = shot.scheduleViewOnly ? ['view'] : ['schedule', 'start', 'work', 'view', 'history', 'supplement']
  return shotActions(shot).filter(action => keys.includes(action.key))
}
function workAction(shot) {
  if (shot.allowedActions?.includes('task.work') && hasPermission('shotgrid:task:query')) {
    if (shot.status === 'reviewing') {
      return { label: '追加审核文件', type: 'task', tone: '', supplemental: true, hint: '用于提交审核后补充文件；审核文件应在提交时准备完整。', icon: Upload }
    }
    const label = shot.status === 'revision' ? '去修改' : '去做任务'
    return { label, type: 'task', tone: shot.status === 'revision' ? 'warning' : 'primary' }
  }
  if (shot.allowedActions?.includes('task.reopenReview') && hasPermission('shotgrid:version:reopen')) return { label: '重新审核', type: 'review', tone: 'warning' }
  if (shot.allowedActions?.includes('task.review') && shot.latestVersion?.versionId && hasPermission('shotgrid:reviewList:query') && hasPermission('shotgrid:version:query')) {
    return { label: '审核任务', type: 'review', tone: 'primary', color: '#8b5cf6' }
  }
  if (shot.allowedActions?.includes('task.appendIssue') && shot.latestVersion?.versionId && hasPermission('shotgrid:reviewList:query') && hasPermission('shotgrid:version:query') && hasPermission('shotgrid:note:add')) {
    return { label: '追加发送问题', type: 'review', tone: '', supplemental: true, hint: '用于退回后补充遗漏问题；完整反馈应在审核时填写。', icon: Edit }
  }
  return null
}
async function openWork(shot) {
  const action = workAction(shot)
  if (!action || openingWorkShotId.value) return
  const projectId = currentProjectId.value
  openingWorkShotId.value = shot.shotId
  try {
    let target = `/tasks/${shot.taskId}`
    if (action.type === 'review') {
      const response = await getVersionDetail(shot.latestVersion.versionId)
      if (disposed || projectId !== currentProjectId.value) return
      if (Number(response.data?.taskId) !== Number(shot.taskId)) throw new Error('审核版本与任务不匹配，请刷新列表')
      const reviewId = response.data?.autoReviewList?.reviewListId
      if (!reviewId) throw new Error('当前版本没有可用的自动审核单，请刷新列表')
      target = `/reviews/${reviewId}`
    }
    if (disposed || projectId !== currentProjectId.value) return
    workDrawerProjectId.value = projectId
    workDrawer.value?.open(target)
  } catch (error) {
    if (!disposed && projectId === currentProjectId.value) ElMessage.error(error.message || '任务入口加载失败')
  } finally {
    openingWorkShotId.value = null
  }
}
async function handleWorkDrawerClosed() {
  const projectId = workDrawerProjectId.value
  workDrawerProjectId.value = null
  if (disposed || projectId !== currentProjectId.value) return
  try {
    await loadShots(null, true)
  } catch {
    if (!disposed && projectId === currentProjectId.value) ElMessage.warning('列表状态刷新失败，请点击刷新重试')
  }
}
const detailShotId = ref(null)
const showCreate = ref(false)
const showImport = ref(false)
const showEdit = ref(false)
const editingShot = ref(null)
const editField = ref('')
const editAnchor = shallowRef(null)
const editContext = ref(null)
const deleting = ref(false)
const assigning = ref(false)
const startingOperation = ref(null)
const batchStartContext = ref(null)
const adjustmentContext = ref(null)
const currentTime = useCurrentTime()
const { startDialog, requestStartDialog, closeStartDialog, finishStartDialog, failStartDialog } = useTaskStartDialog()
const reordering = ref(false)
const sceneOrderFullyLoaded = ref(false)
const sceneOrderMode = ref(false)
const showHierarchyCreate = ref(false)
const hierarchyCreateMode = ref('episode')
const showBatchAssign = ref(false)
const editingShotId = ref(null)
const singleAssignContext = ref(null)
const assigningShotId = ref(null)
let singleAssignController = null
const createProjectId = ref(null)
const createInitialEpisodeId = ref('')
const createInitialSceneId = ref('')
const importProjectId = ref(null)
const createOperationGeneration = ref(null)
const importOperationGeneration = ref(null)
const projectContextForm = ref(null)
const shotFilterForm = ref(null)
const batchAssignFormRef = ref(null)
const columnSettingsFormRef = ref(null)
const shotTableRef = ref(null)
const shotPageRef = ref(null)
const shotTableHeight = ref(320)
const resultsShotId = ref(null)
const resultsPanel = ref(null)
let pendingBrowseRestore = null
let tableScrollPosition = { top: 0, left: 0 }
const resultsIndex = computed(() => shots.value.findIndex(row => Number(row.shotId) === resultsShotId.value))
async function moveShotResults(offset) {
  if (batchBusy.value || shotsLoading.value) return
  const row = shots.value[resultsIndex.value + offset]
  if (!row) return
  await openShotResults(row)
  if (resultsShotId.value !== Number(row.shotId)) return
  await nextTick()
  const element = shotTableRef.value?.$el.querySelectorAll('.el-table__body-wrapper .el-table__row')[resultsIndex.value]
  const viewport = shotTableRef.value?.$el.querySelector('.el-scrollbar__wrap')
  if (element && viewport) {
    if (element.offsetTop < viewport.scrollTop) shotTableRef.value.setScrollTop(element.offsetTop)
    else if (element.offsetTop + element.offsetHeight > viewport.scrollTop + viewport.clientHeight) shotTableRef.value.setScrollTop(element.offsetTop + element.offsetHeight - viewport.clientHeight)
  }
}
function navigateShotByKey(event) {
  if (!resultsShotId.value || viewMode.value !== 'table' || event.defaultPrevented || event.repeat || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || !['ArrowUp', 'ArrowDown'].includes(event.key)) return
  if (event.target?.closest('input, textarea, select, button, a, video, [contenteditable], [role="combobox"], [role="listbox"], [role="slider"]')) return
  if ([...document.querySelectorAll('.el-dialog, .el-message-box')].some(element => element.getClientRects().length)) return
  if (event.target !== document.body && !event.target?.closest('.shot-page, .shot-results-drawer')) return
  if (batchBusy.value || shotsLoading.value) return
  event.preventDefault()
  moveShotResults(event.key === 'ArrowUp' ? -1 : 1)
}
function rememberBrowsePosition() {
  if (viewMode.value !== 'table' || sceneOrderMode.value || !appliedQuery.value || appliedQuery.value !== JSON.stringify(query) || shotsError.value || Number(sessionStore.activeProjectId) !== currentProjectId.value) return
  sessionStore.shotBrowseState = { projectId: currentProjectId.value, query: JSON.parse(appliedQuery.value),
    workspaceKey: JSON.stringify(sessionStore.workspaceFilters), permissionsKey: sessionStore.permissions.join('|'),
    pages: loadedShotPage.value, scroll: { ...tableScrollPosition }, shotId: resultsShotId.value }
}
const resultsPreview = ref(false)
let resultsSelectionGeneration = 0
async function openShotResults(row, preview = false) {
  if (Number(row.shotId) === resultsShotId.value && preview) { await resultsPanel.value?.previewApproved(); return }
  if (!hasPermission('shotgrid:shot:query') || !currentProjectId.value || Number(row.shotId) === resultsShotId.value) return
  const expectedProject = currentProjectId.value
  const request = ++resultsSelectionGeneration
  if (resultsPanel.value && !(await resultsPanel.value.canLeave())) return
  if (request !== resultsSelectionGeneration || expectedProject !== currentProjectId.value) return
  resultsPreview.value = preview
  resultsShotId.value = Number(row.shotId)
}
async function beforeCloseResults(done) {
  if (resultsPanel.value && !(await resultsPanel.value.canLeave())) return
  closeShotResults()
  done()
}
function selectShotResults(row, column, event) {
  if (['selection', 'expand'].includes(column?.type) || event?.target?.closest('button, input, a, .el-checkbox, .el-table__expand-icon')) return
  openShotResults(row)
}
function closeShotResults() {
  resultsSelectionGeneration++
  resultsShotId.value = null
}
const tableAvailableWidth = ref(0)
const { mode: tablePresentationMode, widths: tableColumnWidths, rowHeight: tableRowHeight, visibleColumns: visibleDetailColumns, setColumns: setDetailColumns, saveWidth: saveColumnWidth, resetPresentation: resetTablePresentation } = useShotTablePresentation(computed(() => sessionStore.user?.userId), tableAvailableWidth)
const tableSettings = reactive({ mode: tablePresentationMode, rowHeight: tableRowHeight })
const baseColumnWidths = { identity: 132, shotNo: 104, scene: 150, duration: 96, description: 300, plan: 192, assignee: 140, status: 150 }
const tableContentWidth = computed(() => 54 + 40 + 104
  + Object.entries(baseColumnWidths).reduce((sum, [key, width]) => sum + (tableColumnWidths.value[key] || width), 0)
  + shotDetailColumns.filter(column => visibleDetailColumns.value.includes(column.key)).reduce((sum, column) => sum + (tableColumnWidths.value[column.key] || column.width), 0))
const detailColumnCount = computed(() => tableAvailableWidth.value < 1000 ? 1 : 2)
let tableHeightObserver = null
let tableHeightFrame = null

function updateTableHeight() {
  const table = shotTableRef.value?.$el
  if (!table) return
  tableAvailableWidth.value = table.parentElement?.getBoundingClientRect().width || 0
  // 使用页面坐标，避免整页滚动时表格高度反复增减。
  const tableTop = table.getBoundingClientRect().top + window.scrollY
  shotTableHeight.value = Math.max(200, Math.floor(window.innerHeight - tableTop - 18))
}

function scheduleTableHeight() {
  if (tableHeightFrame !== null) cancelAnimationFrame(tableHeightFrame)
  tableHeightFrame = requestAnimationFrame(() => {
    tableHeightFrame = null
    updateTableHeight()
  })
}

watch(shotTableRef, () => {
  tableHeightObserver?.disconnect()
  if (shotTableRef.value && shotPageRef.value && typeof ResizeObserver !== 'undefined') {
    tableHeightObserver = new ResizeObserver(scheduleTableHeight)
    // 只限制最大高度；镜头较少时表格按内容收起。
    for (const element of shotPageRef.value.children) tableHeightObserver.observe(element)
    tableHeightObserver.observe(shotPageRef.value)
  }
  scheduleTableHeight()
}, { flush: 'post' })

onMounted(() => { window.addEventListener('resize', scheduleTableHeight); document.addEventListener('keydown', navigateShotByKey) })
onBeforeUnmount(() => {
  rememberBrowsePosition()
  document.removeEventListener('keydown', navigateShotByKey)
  window.removeEventListener('resize', scheduleTableHeight)
  tableHeightObserver?.disconnect()
  if (tableHeightFrame !== null) cancelAnimationFrame(tableHeightFrame)
})
const projectContext = reactive({ projectId: '', scope: '' })
const batchAssignForm = reactive({ assigneeUserId: '', rows: [] })
const batchAssignTable = ref(null)
const batchAssignChecked = ref([])
const batchAssignAttempted = ref(false)
const batchAssignError = ref('')
let batchAssignProject = null
let batchAssignGeneration = 0
const batchAssignCounts = computed(() => {
  const counts = new Map()
  for (const row of batchAssignForm.rows) {
    const key = row.assigneeUserId
    counts.set(key, (counts.get(key) || 0) + 1)
  }
  return [...counts].map(([id, count]) => ({ id, count, name: id ? shotAssigneeName(creatorMembers.value.find(member => String(member.userId) === id)) : '未指定' }))
})
const query = reactive({
  hasFinal: '', keyword: '', episodeId: '', sceneId: '', shotNoStart: '', shotNoEnd: '', shotStatus: '', shotStatuses: [], assigneeUserId: '',
  pageNum: 1, pageSize: 100, orderByColumn: 'sortOrder', isAsc: 'ascending'
})
const appliedQuery = ref('')
const appliedShotRange = ref({ shotNoStart: null, shotNoEnd: null })
let projectController = null
let shotController = null
let moreController = null
let appliedShotParams = null
const loadedShotPage = ref(1)
const loadingMore = ref(false)
const refreshingShots = ref(false)
const moreError = ref('')
const loadMoreRef = ref(null)
let moreObserver = null
let sceneController = null
let episodeRefreshController = null
let disposed = false
let operationGeneration = 0
let projectGeneration = 0
let rowSortable = null
let syncingShotSelection = false
const MAX_SCENE_SORT_SHOTS = 2000

const wildcard = computed(() => sessionStore.permissions.includes('*:*:*'))
const hasPermission = permission => wildcard.value || sessionStore.permissions.includes(permission)
useVersionCollectionRealtime(computed(() => hasPermission('shotgrid:version:query')
  ? shots.value.map(shot => shot.latestVersion?.versionId).filter(Boolean) : []), async () => {
  if (disposed || shotsLoading.value || loadingMore.value || assigning.value || deleting.value || reordering.value ||
      startingOperation.value || adjustmentContext.value || directFeedbackOpen.value || showEdit.value || singleAssignContext.value ||
      appliedQuery.value !== JSON.stringify(query)) return
  await loadShots(null, true)
})
const canViewAll = computed(() => hasPermission('shotgrid:project:all'))
const isDirector = computed(() => myProjectRoles(project.value).includes('director') || wildcard.value || canViewAll.value)
const projectAllowsWrites = computed(() => project.value && !['completed', 'archived'].includes(project.value.projectStatus) && project.value.storageStatus === 'ready')
const canCreate = computed(() => isDirector.value && hasPermission('shotgrid:shot:add') && projectAllowsWrites.value)
const canImport = computed(() => isDirector.value && hasPermission('shotgrid:shot:import') && projectAllowsWrites.value)
const canEdit = computed(() => isDirector.value && hasPermission('shotgrid:shot:edit') && projectAllowsWrites.value)
const canDelete = computed(() => isDirector.value && hasPermission('shotgrid:shot:archive') && projectAllowsWrites.value)
const canAssign = computed(() => isDirector.value && hasPermission('shotgrid:task:assign') && projectAllowsWrites.value)
// 镜头分配后自动制作，不再暴露人工开工入口。
const canStart = computed(() => false)
const canSchedule = computed(() => Boolean(
  project.value
  && isDirector.value
  && hasPermission('shotgrid:task:schedule')
  && !['completed', 'archived'].includes(project.value.projectStatus)
))
const startDisabled = computed(() => shotsLoading.value || Boolean(adjustmentContext.value) || Boolean(startingOperation.value) || directFeedbackOpen.value || assigning.value || deleting.value || reordering.value)
const canCreateEpisode = computed(() => isDirector.value && hasPermission('shotgrid:episode:add') && projectAllowsWrites.value)
const canCreateScene = computed(() => isDirector.value && hasPermission('shotgrid:scene:add') && projectAllowsWrites.value)
const isSceneOrderScope = computed(() => (
  viewMode.value === 'table' &&
  Boolean(query.episodeId) &&
  Boolean(query.sceneId) &&
  !query.keyword.trim() &&
  !query.shotStatus && !query.shotStatuses.length &&
  !query.assigneeUserId && !query.hasFinal &&
  !query.shotNoStart.trim() && !query.shotNoEnd.trim() &&
  query.orderByColumn === 'sortOrder' &&
  query.isAsc === 'ascending'
))
const sceneSequenceConsistent = computed(() => (
  shots.value.every((shot, index) => {
    const expected = index + 1
    return (
      Number(shot?.sequencePosition) === expected &&
      Number(shot?.shotNo) === expected &&
      shot?.shotCode === formatShotCode(expected)
    )
  })
))
const canDragSort = computed(() => (
  canEdit.value &&
  !shotsLoading.value &&
  !reordering.value &&
  sceneOrderMode.value &&
  isSceneOrderScope.value &&
  sceneOrderFullyLoaded.value &&
  sceneSequenceConsistent.value &&
  shots.value.length > 1
))
const dragSortHint = computed(() => {
  if (!shotFeatures.manualSortEnabled || !canEdit.value || viewMode.value !== 'table' || shotsLoading.value) return ''
  if (!query.episodeId) return ' · 选择具体集和场次后可排序'
  if (!query.sceneId) return ' · 请选择具体场次后可排序'
  if (query.hasFinal || query.keyword.trim() || query.shotStatus || query.shotStatuses.length || query.assigneeUserId || query.shotNoStart.trim() || query.shotNoEnd.trim()) return ' · 清空附加筛选后可排序'
  if (total.value > MAX_SCENE_SORT_SHOTS) return ` · 当前场次超过 ${MAX_SCENE_SORT_SHOTS} 镜，不能在线拖拽排序`
  if (!sceneOrderMode.value) return ''
  if (shotsError.value) return ' · 完整场次加载失败，请重试或退出排序模式'
  if (!sceneOrderFullyLoaded.value) return ' · 正在加载完整场次，完成后可排序'
  if (!sceneSequenceConsistent.value) return ' · 当前场次镜头号不连续，请先完成历史数据治理后再排序'
  if (shots.value.length <= 1) return ' · 当前场次无需排序'
  if (!shots.value.some(isShotOrderMutable)) return ' · 当前场次镜头均已冻结，不能调整顺序'
  return ' · 拖动左侧手柄调整顺序，镜头号会同步更新；已开始制作或目录已冻结的镜头不可调整'
})
const currentProjectId = computed(() => {
  try { return assertPositiveId(projectContext.projectId, '项目') } catch { return null }
})
const scheduleInitialFilters = computed(() => ({
  productionFrom: sessionStore.workspaceFilters.productionFrom || undefined,
  productionTo: sessionStore.workspaceFilters.productionTo || undefined,
  keyword: query.keyword.trim(),
  assigneeUserIds: query.assigneeUserId ? [Number(query.assigneeUserId)] : [],
  episodeIds: query.episodeId ? [Number(query.episodeId)] : [],
  sceneIds: query.sceneId ? [Number(query.sceneId)] : [],
  ...appliedShotRange.value,
  taskStatuses: (query.shotStatuses.length ? query.shotStatuses : query.shotStatus ? [query.shotStatus] : []).filter(value => !['unassigned', 'pending_info'].includes(value)).map(value => value === 'reviewing' ? 'pending_review' : value)
}))
const creatorMembers = computed(() => members.value.filter(member => memberRoles(member).includes('creator')))
const selectedShots = computed(() => shots.value.filter(shot => selectedShotIds.value.has(Number(shot.shotId))))
const hasAssignedSelection = computed(() => selectedShots.value.some(shot => Boolean(shot.assignee)))
const batchAssignLabel = computed(() => hasAssignedSelection.value ? '批量重新分配' : '批量分配')
const detailShot = computed(() => shots.value.find(shot => Number(shot.shotId) === detailShotId.value) || null)
const detailDrawerTitle = computed(() => detailShot.value ? `制作履历 · ${detailShot.value.shotCode}` : '制作履历')
const canDeleteSelection = computed(() => Boolean(selectedShots.value.length) && selectedShots.value.every(shot => canDeleteShot(shot)))
const { pollingError } = useTaskStatePolling({
  getDelay: () => {
    if (!projectAllowsWrites.value || shotsLoading.value || loadingMore.value || scenesLoading.value || shotsError.value ||
        showDetail.value || workDrawerProjectId.value || showCreate.value || showImport.value || showEdit.value || editingShotId.value ||
        showHierarchyCreate.value || showBatchAssign.value || startingOperation.value || adjustmentContext.value || directFeedbackOpen.value || singleAssignContext.value || assigningShotId.value ||
        deleting.value || assigning.value || reordering.value || appliedQuery.value !== JSON.stringify(query)) return null
    if (shots.value.some(shot => shot.status === 'preparing')) return 1500
    return shots.value.some(shot => shot.status === 'not_started') ? 5000 : null
  },
  refresh: controller => loadShots(controller, true)
})
const optionalPositiveIdRule = message => ({
  validator: (_rule, value, callback) => {
    if (!value) {
      callback()
      return
    }
    const id = Number(value)
    if (!Number.isSafeInteger(id) || id <= 0) {
      callback(new Error(message))
      return
    }
    callback()
  },
  trigger: 'change'
})
const projectContextRules = {
  projectId: [optionalPositiveIdRule('请选择有效项目')],
  scope: [{
    validator: (_rule, value, callback) => {
      if (!['', 'all'].includes(value)) {
        callback(new Error('请选择有效项目范围'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}
function shotRangeError() {
  if (!query.sceneId) return ''
  for (const value of [query.shotNoStart, query.shotNoEnd]) {
    if (value.trim() && (!/^[0-9]+$/.test(value.trim()) || Number(value) < 1 || Number(value) > 2147483647)) {
      return '镜头号须为 1 至 2147483647 的整数'
    }
  }
  if (query.shotNoStart.trim() && query.shotNoEnd.trim() && Number(query.shotNoStart) > Number(query.shotNoEnd)) {
    return '起始镜头号不能大于结束镜头号'
  }
  return ''
}
const shotRangeRule = {
  validator: (_rule, _value, callback) => {
    const message = shotRangeError()
    callback(message ? new Error(message) : undefined)
  },
  trigger: 'blur'
}
const shotFilterRules = {
  shotNoStart: [shotRangeRule],
  shotNoEnd: [shotRangeRule],
  keyword: [{ max: 200, message: '搜索内容不能超过 200 个字符', trigger: 'blur' }],
  episodeId: [optionalPositiveIdRule('请选择有效集')],
  sceneId: [optionalPositiveIdRule('请选择有效场次')],
  shotStatus: [{
    validator: (_rule, value, callback) => {
      if (value && !['pending_info', 'unassigned', 'pending_schedule', 'not_started', 'preparing', 'in_progress', 'reviewing', 'revision', 'completed'].includes(value)) {
        callback(new Error('请选择有效镜头状态'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  assigneeUserId: [optionalPositiveIdRule('请选择有效制作人')]
}
const batchAssigneeRules = [{ validator: (_rule, value, callback) => {
  callback(creatorMembers.value.some(member => String(member.userId) === value) ? undefined : new Error('请选择项目制作人'))
}, trigger: 'change' }]
const batchAssignRules = {
  assigneeUserId: [{ validator: (_rule, value, callback) => {
    callback(!value || creatorMembers.value.some(member => String(member.userId) === value) ? undefined : new Error('请选择有效制作人'))
  }, trigger: 'change' }]
}
async function applyBatchAssignee() {
  if (assigning.value || batchAssignAttempted.value) return
  if (!await batchAssignFormRef.value.validateField('assigneeUserId').catch(() => false)) return
  if (!batchAssignForm.assigneeUserId) return ElMessage.warning('请先选择制作人')
  for (const row of batchAssignChecked.value) row.assigneeUserId = batchAssignForm.assigneeUserId
  batchAssignFormRef.value.clearValidate()
}

function shotTimeState(shot) {
  return taskTimeReminder({ taskStatus: shot.status, expectedEndTime: shot.expectedEndTime }, currentTime.value)
}

function canAdjustShot(shot) {
  return isDirector.value && projectAllowsWrites.value && hasPermission('shotgrid:task:edit') && hasPermission('shotgrid:task:query') && hasPermission('shotgrid:shot:query') && shot?.status === 'in_progress' && shot.allowedActions?.includes('task.adjust')
}
function openProductionAdjustment(targets, initialFields = []) {
  if (startDisabled.value || !targets.length || targets.length > 100 || !targets.every(canAdjustShot)) return
  const projectId = currentProjectId.value
  const generation = projectGeneration
  const snapshot = targets.map(shot => ({ ...shot }))
  adjustmentContext.value = { projectId, shots: snapshot, initialFields, members: [...creatorMembers.value], permissions: [...sessionStore.permissions],
    validateContext: () => !disposed && Boolean(adjustmentContext.value) && currentProjectId.value === projectId && generation === projectGeneration
  }
}
async function closeProductionAdjustment(result = {}) {
  const completed = result.saved ? adjustmentContext.value?.shots.map(shot => Number(shot.shotId)) || [] : []
  adjustmentContext.value = null
  if (result.saved || result.attempted) await refreshAfterBatch(completed)
}

function canStartShot(shot) {
  return Boolean(
    canStart.value && hasPermission('shotgrid:shot:query') && shot?.status === 'not_started' &&
    shot.allowedActions?.includes('task.start') &&
    (shot.expectedStartTime || shot.task?.expectedStartTime) &&
    (shot.expectedEndTime || shot.task?.expectedEndTime) &&
    Number.isSafeInteger(shot.taskId) && shot.taskId > 0 &&
    Number.isSafeInteger(shot.taskLockVersion) && shot.taskLockVersion >= 0 &&
    Number.isSafeInteger(shot.lockVersion) && shot.lockVersion >= 0
  )
}

function isCurrentStart(operation) {
  return !disposed && startingOperation.value === operation &&
    currentProjectId.value === operation.projectId && projectGeneration === operation.projectGeneration
}

function canScheduleShot(shot) {
  return Boolean(canSchedule.value && hasPermission('shotgrid:shot:query') && !['pending_info', 'unassigned', 'completed'].includes(shot?.status) &&
    Number.isSafeInteger(shot.taskId) && shot.taskId > 0 && Number.isSafeInteger(shot.taskLockVersion) &&
    Number.isSafeInteger(shot.lockVersion))
}
function openBatchStart(mode = 'start', targets = selectedShots.value, single = false) {
  const eligible = mode === 'schedule' ? canScheduleShot : canStartShot
  if (startDisabled.value || !targets.length || !targets.every(eligible) || targets.length > 100) return
  const operation = Object.freeze({ projectId: currentProjectId.value, projectGeneration })
  const snapshot = targets.map(shot => ({ ...shot }))
  startingOperation.value = operation
  batchStartContext.value = {
    projectId: operation.projectId, shots: snapshot, members: [...members.value], mode, single, canSchedule: canSchedule.value,
    validateContext: () => isCurrentStart(operation) && snapshot.every(shot => {
      const current = shots.value.find(item => item.shotId === shot.shotId) || shot
      return eligible(current) && current.taskId === shot.taskId &&
        current.taskLockVersion === shot.taskLockVersion && current.lockVersion === shot.lockVersion
    })
  }
}

async function closeBatchStart(result = {}) {
  batchStartContext.value = null
  startingOperation.value = null
  if (result.attempted || result.completedShotIds?.length) await refreshAfterBatch(result.completedShotIds || [])
}

async function confirmStartShot(shot) {
  if (!canStartShot(shot) || startDisabled.value) return
  const operation = Object.freeze({
    projectId: currentProjectId.value, projectGeneration,
    shotId: shot.shotId, taskId: shot.taskId,
    lockVersion: shot.taskLockVersion, shotLockVersion: shot.lockVersion
  })
  let scheduleChanged = false
  startingOperation.value = operation
  try {
    const detailResponse = await getShotDetail(operation.projectId, operation.shotId)
    if (!isCurrentStart(operation)) return
    const detail = detailResponse.data
    if (!detail?.allowedActions?.includes('task.start') || detail.task?.taskId !== operation.taskId ||
      detail.task.lockVersion !== operation.lockVersion || detail.lockVersion !== operation.shotLockVersion) {
      ElMessage.warning('镜头或任务已发生变化，请刷新后重新确认开工。')
      await loadShots()
      return
    }
    const response = await requestStartDialog({
      canSchedule: canSchedule.value,
      onScheduleSaved: () => { scheduleChanged = true },
      name: [detail.episodeCode, detail.sceneCode, detail.shotCode].join(' / '),
      assigneeName: shotAssigneeName(detail.task.assignee || shot.assignee, members.value),
      shot: detail, task: detail.task, taskId: operation.taskId,
      command: { lockVersion: operation.lockVersion, shotLockVersion: operation.shotLockVersion, assetsConfirmed: true },
      validateContext: () => {
        const currentShot = shots.value.find(item => item.shotId === operation.shotId) || shot
        return isCurrentStart(operation) && canStartShot(currentShot) && currentShot.taskId === operation.taskId &&
          currentShot.taskLockVersion === operation.lockVersion && currentShot.lockVersion === operation.shotLockVersion
      }
    })
    if (!isCurrentStart(operation)) {
      ElMessage.success('原镜头任务已确认开工，请返回原项目查看。')
      return
    }
    ElMessage.success(response.data?.taskStatus === 'preparing'
      ? '已确认开工，正在准备制作目录'
      : '已确认开工，负责人可以开始制作')
    closeDetailDrawer()
    await loadShots()
    scheduleChanged = false
  } catch (error) {
    if (error === 'cancel' || error === 'close' || !isCurrentStart(operation)) return
    ElMessage.error(error?.message || '确认开工失败，请刷新后重试')
    if (Number(error?.httpStatus || error?.status) === 409) await loadShots()
  } finally {
    if (scheduleChanged && isCurrentStart(operation)) await loadShots()
    if (startingOperation.value === operation) startingOperation.value = null
  }
}

function canDeleteShot(shot) {
  return canDelete.value && ['pending_info', 'unassigned', 'pending_schedule', 'not_started'].includes(shot?.status)
}

function canEditShot(shot) {
  return canEdit.value && ['pending_info', 'unassigned', 'pending_schedule', 'not_started'].includes(shot?.status)
}

function canEditField(shot, field) {
  if (['shotNo', 'scene'].includes(field)) return canEditShot(shot) && shot.allowedActions?.includes('shot.editIdentity')
  return canEditShot(shot)
}
function fieldReadOnlyReason(shot, field) {
  if (canEditField(shot, field) || (canAdjustShot(shot) && !['shotNo', 'scene'].includes(field))) return '点击编辑'
  if (['shotNo', 'scene'].includes(field) && (shot.storageDirName || shot.directoryStatus !== 'not_created')) return '已有制作目录，镜头号和场次已冻结'
  return isDirector.value ? '当前制作阶段不可修改此项' : '需要项目管理人员及编辑权限'
}
function editCell(shot, field, event) {
  if (showEdit.value || editingShotId.value || startDisabled.value) return
  if (canEditField(shot, field)) return openEditDialog(shot, field, event)
  if (canAdjustShot(shot) && !['shotNo', 'scene'].includes(field)) return openProductionAdjustment([shot])
  ElMessage.info(fieldReadOnlyReason(shot, field))
}
function editProducer(shot) {
  if (canOpenShotAssign(shot)) return openSingleAssign(shot)
  if (canAdjustShot(shot)) return openProductionAdjustment([shot])
  ElMessage.info(shot.status === 'pending_info' ? '请先填写制作内容，再分配制作人' : '当前阶段或权限不允许调整制作人')
}
function statusActions(shot) {
  return shotActions(shot).filter(action => ['feedback', 'start', 'work', 'supplement', 'view'].includes(action.key))
}
function moreActions(shot) {
  return shotActions(shot).filter(action => ['history', 'view', 'delete'].includes(action.key))
}

function canAssignShot(shot) {
  return canAssign.value && Boolean(shot?.allowedActions?.includes('task.assign'))
}

function canOpenShotAssign(shot) {
  return canAssignShot(shot) && hasPermission('shotgrid:shot:query')
}

function closeSingleAssign() {
  singleAssignController?.abort()
  singleAssignContext.value = null
  assigningShotId.value = null
}

async function openSingleAssign(shot) {
  if (!canOpenShotAssign(shot) || shotsLoading.value || assigningShotId.value || singleAssignContext.value ||
    deleting.value || assigning.value || startingOperation.value) return
  const projectId = currentProjectId.value
  const shotId = Number(shot.shotId)
  const generation = ++operationGeneration
  const request = new AbortController()
  singleAssignController = request
  assigningShotId.value = shotId
  try {
    const response = await getShotDetail(projectId, shotId, { signal: request.signal })
    if (disposed || request.signal.aborted || singleAssignController !== request || currentProjectId.value !== projectId) return
    const current = response.data
    if (Number(current?.projectId) !== projectId || Number(current?.shotId) !== shotId ||
      !canOpenShotAssign(current) || !current.allowedActions?.includes('task.assign')) {
      ElMessage.warning('镜头状态或权限已变化，当前不能分配制作人。')
      await loadShots()
      return
    }
    singleAssignContext.value = Object.freeze({
      projectId, shotId, operationGeneration: generation,
      shot: Object.freeze({ ...current, task: current.task ? Object.freeze({ ...current.task }) : null })
    })
  } catch (error) {
    if (!disposed && !request.signal.aborted) ElMessage.error(error?.message || '镜头任务信息加载失败')
  } finally {
    if (singleAssignController === request) assigningShotId.value = null
  }
}

async function handleSingleAssigned(_result, operation) {
  const context = singleAssignContext.value
  if (disposed || !context || context.projectId !== Number(operation?.projectId) ||
    context.shotId !== Number(operation?.shotId) || context.operationGeneration !== Number(operation?.operationGeneration)) return
  closeSingleAssign()
  ElMessage.success(operation.wasReassign ? '镜头任务已改派' : '镜头任务已分配')
  await loadShots()
}

async function refreshSingleAssign() {
  closeSingleAssign()
  ElMessage.info('请从刷新后的镜头重新打开分配操作。')
  await loadShots()
}

function canAddOverallFeedback(shot) {
  return projectAllowsWrites.value && hasPermission('shotgrid:note:add') && hasPermission('shotgrid:version:review')
    && shot.allowedActions?.includes('task.review') && shot.latestVersion?.status === 'pending_review'
}
function canAppendShotIssue(shot) {
  return projectAllowsWrites.value && isDirector.value && hasPermission('shotgrid:note:add') &&
    hasPermission('shotgrid:version:review') && hasPermission('shotgrid:version:query') &&
    ['revision', 'completed'].includes(shot?.status) &&
    shot.allowedActions?.includes('task.appendIssue') && ['rejected', 'final'].includes(shot.latestVersion?.status) &&
    Number.isSafeInteger(shot.latestVersion?.versionId) && shot.latestVersion.versionId > 0
}
function canDirectFeedback(shot) {
  return hasPermission('shotgrid:task:query') && hasPermission('shotgrid:version:query') &&
    (canAddOverallFeedback(shot) || canAppendShotIssue(shot))
}
const batchBusy = computed(() => startDisabled.value || showBatchAssign.value || Boolean(singleAssignContext.value))
const selectableShotCount = computed(() => shots.value.filter(canSelectShot).length)
function batchDisabledReason(kind) {
  if (batchBusy.value) return '请等待当前操作完成'
  if (!selectedShots.value.length) return '请先勾选左侧复选框，可跨场次多选镜头'
  if (selectedShots.value.length > 100) return '每次最多操作 100 个镜头，请减少选择'
  if (kind === 'feedback') return selectedShots.value.every(canDirectFeedback) ? '' : '反馈需要最新待审核或已反馈版本及审核权限，请取消不符合条件的镜头'
  if (kind === 'schedule') return selectedShots.value.every(canScheduleShot) ? '' : '修改周期需要已分配的未完成任务及排期权限，请取消不符合条件的镜头'
  if (selectedShots.value.every(canAssignShot)) return ''
  if (hasPermission('shotgrid:task:assign') && selectedShots.value.every(canAdjustShot)) return ''
  return '请分别选择待分配镜头或可调整的制作中镜头；待审核、反馈和已通过镜头需按各自流程处理'
}
function selectAllShots() {
  if (batchBusy.value) return
  if (viewMode.value === 'storyboard') { storyboardSelection.value = shots.value.filter(canSelectShot).map(shot => Number(shot.shotId)); return }
  shots.value.filter(canSelectShot).forEach(shot => shotTableRef.value?.toggleRowSelection(shot, true, false))
}
function openBatchProducer() {
  if (batchDisabledReason('assign')) return
  if (selectedShots.value.every(canAssignShot)) openBatchAssignDialog()
  else openProductionAdjustment(selectedShots.value, ['assigneeUserId'])
}
function openDirectFeedback(targets = selectedShots.value) {
  if (startDisabled.value || directFeedbackOpen.value || !targets.length) return
  if (targets.length > 100) return ElMessage.warning('一次最多选择 100 个镜头')
  if (!targets.every(canDirectFeedback)) return ElMessage.warning('请只选择已有待审核或已反馈版本、且当前可反馈的镜头；未提交或已通过的镜头不能添加反馈')
  const projectId = currentProjectId.value
  const generation = projectGeneration
  const snapshot = targets.map(shot => ({ shotId: shot.shotId, taskId: shot.taskId ?? shot.task?.taskId,
    versionId: shot.latestVersion.versionId, label: `${shot.episodeCode} / ${shot.sceneCode} / ${shot.shotCode} · ${shot.latestVersion.versionNumber}` }))
  directFeedbackDialog.value?.open(projectId, snapshot, () => !disposed && generation === projectGeneration && currentProjectId.value === projectId)
}
async function closeDirectFeedback(result) {
  if (result.projectId !== currentProjectId.value) return
  if (result.changed || result.uncertain) await refreshAfterBatch(result.completedShotIds || [])
}
async function refreshAfterBatch(completedIds) {
  const completed = new Set(completedIds.map(Number))
  selectedShotIds.value = new Set([...selectedShotIds.value].filter(id => !completed.has(id)))
  try { await loadShots(null, true) }
  catch { await syncShotTableSelection(); ElMessage.warning('操作结果已保留，列表刷新失败，请手动刷新后核对') }
}

function canSelectShot(shot) {
  return (hasPermission('shotgrid:shot:forceDelete') && (shot?.allowedActions || []).includes('shot.forceDelete')) || canScheduleShot(shot) || canAdjustShot(shot) || canAssignShot(shot) || canDeleteShot(shot) || canAddOverallFeedback(shot) || canStartShot(shot) || canAppendShotIssue(shot)
}

function isShotSelectable(shot) {
  return !deleting.value && !assigning.value && !startingOperation.value && !directFeedbackOpen.value && !adjustmentContext.value && canSelectShot(shot)
}

async function fetchAllPages(loader, baseParams, signal) {
  const rows = []
  let pageNum = 1
  let hasMore = true
  while (hasMore) {
    const response = await loader({ ...baseParams, pageNum, pageSize: 100 }, { signal })
    rows.push(...(Array.isArray(response.rows) ? response.rows : []))
    hasMore = Boolean(response.hasNext) && pageNum < 100
    pageNum += 1
  }
  return rows
}

async function loadProjects(preferredId = null) {
  projectController?.abort()
  const controller = new AbortController()
  projectController = controller
  projectsLoading.value = true
  projectsError.value = null
  try {
    projects.value = await sessionStore.loadWorkspaceProjects({ signal: controller.signal })
    const routeId = preferredId || route.query.projectId
    const candidate = projects.value.find(item => String(item.projectId) === String(routeId)) || projects.value[0]
    projectContext.projectId = candidate ? String(candidate.projectId) : ''
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') {
      projects.value = []
      projectContext.projectId = ''
      projectsError.value = shotErrorState(error, '项目范围加载失败')
    }
  } finally {
    if (projectController === controller) projectsLoading.value = false
  }
}

async function loadProjectContext() {
  projectGeneration += 1
  adjustmentContext.value = null
  closeStartDialog()
  batchStartContext.value = null
  startingOperation.value = null
  const projectId = currentProjectId.value
  directFeedbackOpen.value = false
  closeDetailDrawer()
  shotController?.abort()
  moreController?.abort()
  headerSceneController?.abort()
  headerFilterKind.value = ''
  loadingMore.value = false
  refreshingShots.value = false
  moreError.value = ''
  appliedShotParams = null
  loadedShotPage.value = 1
  hasNext.value = false
  sceneController?.abort()
  episodeRefreshController?.abort()
  project.value = null
  episodes.value = []
  scenes.value = []
  members.value = []
  shots.value = []
  sceneOrderFullyLoaded.value = false
  clearShotSelection()
  total.value = 0
  if (!projectId) return
  const controller = new AbortController()
  shotController = controller
  shotsLoading.value = true
  shotsError.value = null
  try {
    await router.replace({ query: { ...route.query, projectId: String(projectId) } })
    if (controller.signal.aborted || currentProjectId.value !== projectId) return
    const [detailResponse, episodeRows, memberResponse] = await Promise.all([
      getProjectDetail(projectId, { signal: controller.signal }),
      fetchAllPages(
        (params, options) => getEpisodePage(projectId, params, options),
        { lifecycleStatus: 'active', orderByColumn: 'episodeNo', isAsc: 'ascending' },
        controller.signal
      ),
      fetchAllPages(
        (params, options) => listShotAssignees(projectId, params, options),
        {},
        controller.signal
      )
    ])
    if (disposed || controller.signal.aborted || shotController !== controller) return
    project.value = detailResponse.data
    episodes.value = episodeRows
    members.value = Array.isArray(memberResponse) ? memberResponse : []
    if (query.episodeId && !episodes.value.some(item => String(item.episodeId) === query.episodeId)) {
      query.episodeId = ''
      query.sceneId = ''
    }
    await loadScenes(false)
    if (disposed || controller.signal.aborted || shotController !== controller) return
    await loadShots(controller)
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && shotController === controller) {
      shotsError.value = shotErrorState(error, '项目镜头信息加载失败')
    }
  } finally {
    if (shotController === controller) shotsLoading.value = false
  }
}

async function loadScenes(resetScene = true) {
  sceneController?.abort()
  scenes.value = []
  if (resetScene) query.sceneId = ''
  const projectId = currentProjectId.value
  const episodeId = Number(query.episodeId)
  if (!projectId || !Number.isSafeInteger(episodeId) || episodeId <= 0) return
  const controller = new AbortController()
  sceneController = controller
  scenesLoading.value = true
  try {
    scenes.value = await fetchAllPages(
      (params, options) => getScenePage(projectId, episodeId, params, options),
      { lifecycleStatus: 'active', orderByColumn: 'sceneNo', isAsc: 'ascending' },
      controller.signal
    )
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED') shotsError.value = shotErrorState(error, '场次筛选项加载失败')
  } finally {
    if (sceneController === controller) scenesLoading.value = false
  }
}

async function loadShots(existingController = null, background = false) {
  const projectId = currentProjectId.value
  if (!projectId || shotRangeError()) return
  if (!background && resultsPanel.value && !await resultsPanel.value.canLeave()) return
  if (disposed || projectId !== currentProjectId.value) return
  appliedShotRange.value = {
    shotNoStart: query.sceneId && query.shotNoStart.trim() ? Number(query.shotNoStart) : null,
    shotNoEnd: query.sceneId && query.shotNoEnd.trim() ? Number(query.shotNoEnd) : null
  }
  if (!existingController) shotController?.abort()
  const controller = existingController || new AbortController()
  shotController = controller
  moreController?.abort()
  refreshingShots.value = background
  loadingMore.value = false
  moreError.value = ''
  const restoring = !background ? pendingBrowseRestore : null
  pendingBrowseRestore = null
  const pagesToRefresh = background ? loadedShotPage.value : restoring?.pages || 1
  if (!background) {
    closeShotResults()
    clearShotSelection()
    shotsLoading.value = true
    shotsError.value = null
    sceneOrderFullyLoaded.value = false
    appliedQuery.value = JSON.stringify(query)
  }
  const fullScene = sceneOrderMode.value && canEdit.value && isSceneOrderScope.value
  try {
    const params = {
      keyword: query.keyword.trim() || undefined,
      episodeId: query.episodeId || undefined,
      sceneId: query.sceneId || undefined,
      shotNoStart: query.sceneId && query.shotNoStart.trim() ? Number(query.shotNoStart) : undefined,
      shotNoEnd: query.sceneId && query.shotNoEnd.trim() ? Number(query.shotNoEnd) : undefined,
      hasFinal: query.hasFinal === '' ? undefined : query.hasFinal === 'yes',
      shotStatus: query.shotStatus || undefined,
      shotStatuses: query.shotStatuses.length ? query.shotStatuses.join(',') : undefined,
      assigneeUserId: query.assigneeUserId || undefined,
      productionFrom: sessionStore.workspaceFilters.productionFrom || undefined,
      productionTo: sessionStore.workspaceFilters.productionTo || undefined,
      pageNum: 1,
      pageSize: query.pageSize,
      orderByColumn: query.orderByColumn,
      isAsc: query.isAsc
    }
    let response = await getShotPage(projectId, params, { signal: controller.signal })
    if (disposed || controller.signal.aborted || shotController !== controller) return
    let loadedRows = Array.isArray(response.rows) ? response.rows : []
    const loadedTotal = Number(response.total || 0)
    let lastPage = 1
    // 后台刷新覆盖已加载范围，不能把正在看的长列表缩回第一批。
    while (!fullScene && response.hasNext && lastPage < pagesToRefresh) {
      response = await getShotPage(projectId, { ...params, pageNum: ++lastPage }, { signal: controller.signal })
      if (disposed || controller.signal.aborted || shotController !== controller) return
      loadedRows = [...loadedRows, ...(Array.isArray(response.rows) ? response.rows : [])]
    }
    if (fullScene && loadedTotal <= MAX_SCENE_SORT_SHOTS && loadedRows.length < loadedTotal) {
      loadedRows = await fetchAllPages(
        (pageParams, options) => getShotPage(projectId, pageParams, options),
        { ...params, pageNum: undefined, pageSize: undefined },
        controller.signal
      )
    }
    if (disposed || controller.signal.aborted || shotController !== controller) return
    loadedRows = [...new Map(loadedRows.map(row => [Number(row.shotId), row])).values()]
    shots.value = loadedRows
    if (resultsShotId.value && !loadedRows.some(row => Number(row.shotId) === resultsShotId.value) && !resultsPanel.value?.dirty) closeShotResults()
    loadedShotPage.value = lastPage
    appliedShotParams = params
    selectedShotIds.value = background
      ? new Set(loadedRows.filter(shot => selectedShotIds.value.has(Number(shot.shotId)) && canSelectShot(shot)).map(shot => Number(shot.shotId)))
      : new Set()
    total.value = loadedTotal
    hasNext.value = fullScene && loadedRows.length === loadedTotal
      ? false
      : Boolean(response.hasNext)
    sceneOrderFullyLoaded.value = (
      fullScene &&
      loadedTotal <= MAX_SCENE_SORT_SHOTS &&
      loadedRows.length === loadedTotal
    )
    await syncShotTableSelection()
    if (restoring && !disposed && shotController === controller && !controller.signal.aborted) {
      if (loadedRows.some(row => Number(row.shotId) === restoring.shotId) && hasPermission('shotgrid:shot:query')) resultsShotId.value = restoring.shotId
      await nextTick()
      tableScrollPosition = { ...restoring.scroll }
      shotTableRef.value?.scrollTo({ top: restoring.scroll.top, left: restoring.scroll.left })
    }
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && shotController === controller && !disposed) {
      if (background) throw error
      shots.value = []
      total.value = 0
      shotsError.value = shotErrorState(error, '镜头列表加载失败')
    }
  } finally {
    if (!background && shotController === controller) shotsLoading.value = false
    if (shotController === controller) refreshingShots.value = false
  }
}

async function loadMoreShots() {
  if (!hasNext.value || shotsLoading.value || refreshingShots.value || loadingMore.value || sceneOrderMode.value ||
      !appliedShotParams || appliedQuery.value !== JSON.stringify(query)) return
  const projectId = currentProjectId.value
  const baseController = shotController
  const controller = new AbortController()
  moreController?.abort()
  moreController = controller
  loadingMore.value = true
  moreError.value = ''
  const nextPage = loadedShotPage.value + 1
  try {
    const response = await getShotPage(projectId, { ...appliedShotParams, pageNum: nextPage }, { signal: controller.signal })
    if (disposed || controller.signal.aborted || shotController !== baseController || moreController !== controller || currentProjectId.value !== projectId) return
    const rows = Array.isArray(response.rows) ? response.rows : []
    const merged = new Map(shots.value.map(row => [Number(row.shotId), row]))
    rows.forEach(row => merged.set(Number(row.shotId), row))
    if (response.hasNext && merged.size === shots.value.length) throw new Error('列表数据已变化，请刷新后继续查看')
    shots.value = [...merged.values()]
    selectedShotIds.value = new Set(shots.value.filter(row => selectedShotIds.value.has(Number(row.shotId)) && canSelectShot(row)).map(row => Number(row.shotId)))
    total.value = Number(response.total || 0)
    loadedShotPage.value = nextPage
    hasNext.value = Boolean(response.hasNext)
    await syncShotTableSelection()
  } catch (error) {
    if (!disposed && !controller.signal.aborted && shotController === baseController && moreController === controller) {
      moreError.value = error.message || '后续镜头加载失败，请重试'
    }
  } finally {
    if (moreController === controller) loadingMore.value = false
  }
}

function handleShotTableScroll({ scrollTop, scrollLeft }) {
  tableScrollPosition = { top: Number(scrollTop) || 0, left: Number(scrollLeft) || 0 }
  const viewport = shotTableRef.value?.$el.querySelector('.el-scrollbar__wrap')
  if (viewport?.clientHeight > 0 && viewport.scrollHeight - viewport.clientHeight - scrollTop < 160 && !moreError.value) loadMoreShots()
}

watch([loadMoreRef, viewMode], () => {
  moreObserver?.disconnect()
  if (!loadMoreRef.value || viewMode.value === 'table' || typeof IntersectionObserver === 'undefined') return
  moreObserver = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting) && !moreError.value) loadMoreShots()
  }, { rootMargin: '160px' })
  moreObserver.observe(loadMoreRef.value)
}, { flush: 'post' })

async function toggleSceneOrderMode() {
  if (shotsLoading.value || reordering.value || assigning.value || deleting.value) return
  if (!sceneOrderMode.value && (!canEdit.value || !isSceneOrderScope.value || total.value > MAX_SCENE_SORT_SHOTS)) return
  sceneOrderMode.value = !sceneOrderMode.value
  query.pageNum = 1
  await loadShots()
}

const headerFilterForm = ref(null)
const headerFilterKind = ref('')
const headerFilterDraft = reactive({ episodeId: '', sceneId: '', assigneeUserId: '', dates: [], statuses: [] })
const headerScenes = ref([])
const headerScenesLoading = ref(false)
const headerScenesError = ref('')
let headerSceneController = null
const shotStatusOptions = ['unassigned', 'preparing', 'in_progress', 'reviewing', 'revision', 'completed']
const headerFilterRules = {
  episodeId: [{ validator: (_r, value, done) => done(!value || episodes.value.some(episode => String(episode.episodeId) === value) ? undefined : new Error('请选择当前项目的有效集')), trigger: 'change' }],
  sceneId: [{ validator: (_r, value, done) => done(!value || headerScenes.value.some(scene => String(scene.sceneId) === value) ? undefined : new Error('请选择当前集的有效场次')), trigger: 'change' }],
  assigneeUserId: [optionalPositiveIdRule('请选择有效制作人')],
  statuses: [{ validator: (_r, value, done) => done(value.every(item => shotStatusOptions.includes(item)) ? undefined : new Error('请选择有效状态')), trigger: 'change' }],
  dates: [{ validator: (_r, value, done) => done(!value?.length || value.length === 2 && value.every(item => /^\d{4}-\d{2}-\d{2}$/.test(item)) && value[0] <= value[1] ? undefined : new Error('请选择有效的起止日期')), trigger: 'change' }]
}
const headerFilterAnchor = shallowRef(null)
function openHeaderFilter(kind, event) {
  headerFilterDraft.episodeId = query.episodeId
  headerFilterDraft.sceneId = query.sceneId
  headerFilterDraft.assigneeUserId = query.assigneeUserId
  headerFilterDraft.statuses = query.shotStatuses.length ? [...query.shotStatuses] : query.shotStatus ? [query.shotStatus] : []
  const { productionFrom, productionTo } = sessionStore.workspaceFilters
  headerFilterDraft.dates = productionFrom && productionTo ? [productionFrom, productionTo] : []
  headerFilterAnchor.value = event.currentTarget
  headerFilterKind.value = kind
  if (kind === 'scene') loadHeaderScenes(false)
  nextTick(() => headerFilterForm.value?.clearValidate())
}
async function loadHeaderScenes(resetScene = true) {
  headerSceneController?.abort()
  headerScenes.value = []
  headerScenesError.value = ''
  headerScenesLoading.value = false
  if (resetScene) headerFilterDraft.sceneId = ''
  const projectId = currentProjectId.value
  const episodeId = headerFilterDraft.episodeId
  if (!projectId || !episodeId) return
  const controller = new AbortController()
  headerSceneController = controller
  headerScenesLoading.value = true
  try {
    const rows = await fetchAllPages((params, options) => getScenePage(projectId, episodeId, params, options),
      { lifecycleStatus: 'active', orderByColumn: 'sceneNo', isAsc: 'ascending' }, controller.signal)
    if (!disposed && !controller.signal.aborted && headerSceneController === controller && currentProjectId.value === projectId && headerFilterKind.value === 'scene') headerScenes.value = rows
  } catch (error) {
    if (!controller.signal.aborted && headerSceneController === controller && !disposed) headerScenesError.value = error.message || '场次加载失败，请重试'
  } finally {
    if (headerSceneController === controller) headerScenesLoading.value = false
  }
}
watch(headerFilterKind, kind => {
  if (kind !== 'scene') { headerSceneController?.abort(); headerScenesLoading.value = false }
})
let publishedWorkspaceFilters = ''
function syncWorkspaceFilters(extra = {}) {
  Object.assign(sessionStore.workspaceFilters, { episodeId: query.episodeId, sceneId: query.sceneId, assigneeUserId: query.assigneeUserId, ...extra })
  publishedWorkspaceFilters = JSON.stringify(sessionStore.workspaceFilters)
}
async function applyHeaderFilter() {
  if (shotsLoading.value || headerScenesLoading.value || headerFilterKind.value === 'scene' && headerScenesError.value) return
  if (!await headerFilterForm.value?.validate().catch(() => false)) return
  const kind = headerFilterKind.value
  if (kind === 'scene') {
    sceneController?.abort()
    scenesLoading.value = false
    query.episodeId = headerFilterDraft.episodeId || ''
    query.sceneId = headerFilterDraft.sceneId || ''
    scenes.value = [...headerScenes.value]
  }
  if (kind === 'assignee') query.assigneeUserId = headerFilterDraft.assigneeUserId || ''
  if (kind === 'status') { query.shotStatuses = [...headerFilterDraft.statuses]; query.shotStatus = '' }
  const extra = kind === 'plan' ? { productionFrom: headerFilterDraft.dates?.[0] || '', productionTo: headerFilterDraft.dates?.[1] || '' } : {}
  headerFilterKind.value = ''
  sceneOrderMode.value = false
  query.pageNum = 1
  syncWorkspaceFilters(extra)
  await nextTick()
  await loadShots()
}
function resetHeaderFilter() {
  headerFilterForm.value?.resetFields()
  if (headerFilterKind.value === 'scene') {
    headerSceneController?.abort()
    headerScenesLoading.value = false
    headerScenesError.value = ''
    headerScenes.value = []
    headerFilterDraft.episodeId = ''
    headerFilterDraft.sceneId = ''
  }
  if (headerFilterKind.value === 'assignee') headerFilterDraft.assigneeUserId = ''
  if (headerFilterKind.value === 'status') headerFilterDraft.statuses = []
  if (headerFilterKind.value === 'plan') headerFilterDraft.dates = []
  headerFilterForm.value?.clearValidate()
  return applyHeaderFilter()
}
async function submitFilters() {
  if (!await shotFilterForm.value?.validate().catch(() => false)) return
  sceneOrderMode.value = false
  query.pageNum = 1
  syncWorkspaceFilters()
  await nextTick()
  await loadShots()
}
function changeEpisodeFilter() {
  query.sceneId = ''
  loadScenes(false)
  submitFilters()
}
function resetFilters() {
  sceneOrderMode.value = false
  shotFilterForm.value?.resetFields()
  Object.assign(query, { hasFinal: '', keyword: '', episodeId: '', sceneId: '', shotNoStart: '', shotNoEnd: '', shotStatus: '', shotStatuses: [], assigneeUserId: '', pageNum: 1 })
  shotFilterForm.value?.clearValidate()
  syncWorkspaceFilters({ productionFrom: '', productionTo: '' })
  loadScenes(false)
  loadShots()
}
watch(() => JSON.stringify(sessionStore.workspaceFilters), async value => {
  if (value === publishedWorkspaceFilters) { publishedWorkspaceFilters = ''; return }
  publishedWorkspaceFilters = ''
  if (!currentProjectId.value || !project.value || Number(sessionStore.activeProjectId) !== currentProjectId.value) return
  const { episodeId, sceneId, assigneeUserId } = sessionStore.workspaceFilters
  const episodeChanged = query.episodeId !== episodeId
  Object.assign(query, { episodeId, sceneId, assigneeUserId, pageNum: 1 })
  operationGeneration++
  closeEditDialog()
  closeSingleAssign()
  sceneOrderMode.value = false
  if (episodeChanged) await loadScenes(false)
  if (!disposed) await loadShots()
})

function destroyRowSortable() {
  rowSortable?.destroy()
  rowSortable = null
}

function initRowSortable() {
  destroyRowSortable()
  if (!canDragSort.value || !shotTableRef.value) return
  const tableBody = shotTableRef.value.$el?.querySelector('.el-table__body-wrapper tbody')
  if (!tableBody) return
  rowSortable = Sortable.create(tableBody, {
    animation: 160,
    handle: '.shot-drag-handle',
    filter: '.shot-drag-handle.is-disabled',
    preventOnFilter: true,
    forceFallback: true,
    fallbackOnBody: true,
    fallbackTolerance: 3,
    ghostClass: 'shot-row--ghost',
    chosenClass: 'shot-row--chosen',
    onEnd: handleRowDragEnd
  })
}

function isShotOrderMutable(shot) {
  return (
    ['pending_info', 'unassigned', 'pending_schedule', 'not_started'].includes(shot?.status) &&
    !shot?.storageDirName &&
    shot?.directoryStatus === 'not_created' &&
    !shot?.latestVersion
  )
}

function shotOrderLockReason(shot) {
  if (!['pending_info', 'unassigned', 'pending_schedule', 'not_started'].includes(shot?.status)) return '该镜头已开始制作，不能调整顺序'
  if (shot?.storageDirName || shot?.directoryStatus !== 'not_created') return '该镜头目录已冻结，不能调整顺序'
  if (shot?.latestVersion) return '该镜头已有版本，不能调整顺序'
  return ''
}

async function handleRowDragEnd(event) {
  const oldIndex = Number(event.oldIndex)
  const newIndex = Number(event.newIndex)
  if (
    reordering.value ||
    !Number.isSafeInteger(oldIndex) ||
    !Number.isSafeInteger(newIndex) ||
    oldIndex === newIndex
  ) return
  const target = shots.value[oldIndex]
  if (!target) {
    await loadShots()
    return
  }
  const affectedShots = shots.value.slice(Math.min(oldIndex, newIndex), Math.max(oldIndex, newIndex) + 1)
  const blockedShot = affectedShots.find(shot => !isShotOrderMutable(shot))
  if (blockedShot) {
    ElMessage.warning(`${blockedShot.shotCode}：${shotOrderLockReason(blockedShot)}`)
    await loadShots()
    return
  }
  const reordered = [...shots.value]
  const [moved] = reordered.splice(oldIndex, 1)
  reordered.splice(newIndex, 0, moved)
  shots.value = reordered
  reordering.value = true
  const sequencePosition = newIndex + 1
  try {
    const response = await reorderShot(currentProjectId.value, target.shotId, {
      lockVersion: target.lockVersion,
      sequencePosition
    })
    const result = response?.data || response
    if (result?.operationStatus === 'pending') {
      ElMessage.success(`顺序已受理，正在迁移存量目录；完成后自动更新为 ${formatShotCode(sequencePosition)}`)
      await loadProjectContext()
    } else {
      ElMessage.success(`已调整为本场第 ${sequencePosition} 镜（${result?.shotCode || formatShotCode(sequencePosition)}）`)
    }
  } catch (error) {
    const state = shotErrorState(error, '镜头顺序调整失败')
    ElMessage.error(state.message)
  } finally {
    reordering.value = false
    await loadShots()
  }
}

function openHierarchyCreate(mode) {
  if (mode === 'episode' && !canCreateEpisode.value) return
  if (mode === 'scene') {
    if (!canCreateScene.value) return
    if (!episodes.value.length) {
      ElMessage.warning('请先新建集，再新建场次')
      return
    }
  }
  hierarchyCreateMode.value = mode
  showHierarchyCreate.value = true
}

function closeHierarchyCreate() {
  showHierarchyCreate.value = false
}

async function handleHierarchySaved(result) {
  const entity = result?.entity
  if (!entity) return
  showHierarchyCreate.value = false
  if (result.type === 'episode') {
    query.episodeId = String(entity.episodeId)
    query.sceneId = ''
    ElMessage.success(`${entity.episodeCode} 已创建，请继续新建场次`)
  } else {
    query.episodeId = String(result.episodeId || entity.episodeId)
    query.sceneId = String(entity.sceneId)
    ElMessage.success(`场次 ${entity.sceneCode} 已创建，可直接新建镜头`)
  }
  query.pageNum = 1
  await loadProjectContext()
}

function openShot(shot) {
  const targetShotId = Number(shot?.shotId)
  if (!currentProjectId.value || !Number.isSafeInteger(targetShotId) || targetShotId <= 0) return
  detailShotId.value = targetShotId
  showDetail.value = true
}

function closeDetailDrawer() {
  showDetail.value = false
}

function clearDetailDrawer() {
  detailShotId.value = null
}

async function handleDetailChanged(operationContext) {
  if (
    currentProjectId.value !== Number(operationContext?.projectId) ||
    detailShotId.value !== Number(operationContext?.shotId)
  ) return
  await loadShots()
}

async function handleDetailDeleted(operationContext) {
  if (currentProjectId.value !== Number(operationContext?.projectId)) return
  purgeRefresh.value++
  closeDetailDrawer()
  await loadShots()
}

function handleShotSelectionChange(selection) {
  if (syncingShotSelection) return
  const selectedIds = new Set(selection.map(shot => Number(shot.shotId)))
  selectedShotIds.value = new Set(shots.value
    .filter(shot => selectedIds.has(Number(shot.shotId)) && canSelectShot(shot))
    .map(shot => Number(shot.shotId)))
}

function clearShotSelection() {
  selectedShotIds.value = new Set()
  shotTableRef.value?.clearSelection()
}

async function syncShotTableSelection() {
  await nextTick()
  if (disposed || !shotTableRef.value) return
  // 轮询替换行对象后，仅恢复当前列表中仍有操作权限的选择。
  syncingShotSelection = true
  try {
    shotTableRef.value.clearSelection()
    selectedShots.value.filter(canSelectShot).forEach(shot => {
      shotTableRef.value.toggleRowSelection(shot, true, false)
    })
  } finally {
    syncingShotSelection = false
  }
}

async function confirmBatchAssign() {
  if (assigning.value || batchAssignAttempted.value || !batchAssignForm.rows.length) return
  if (!await batchAssignFormRef.value.validate().catch(() => false)) return
  const targetProjectId = batchAssignProject
  const generation = batchAssignGeneration
  const current = () => !disposed && targetProjectId === currentProjectId.value && generation === projectGeneration
  if (!current()) return
  if (batchAssignForm.rows.some(row => !canAssignShot(row.shot))) return ElMessage.warning('镜头状态或权限已变化，请关闭后刷新重试')
  const groups = new Map()
  for (const row of batchAssignForm.rows) {
    if (!groups.has(row.assigneeUserId)) groups.set(row.assigneeUserId, [])
    groups.get(row.assigneeUserId).push(row)
  }
  assigning.value = true
  batchAssignAttempted.value = true
  try {
    for (const [userId, rows] of groups) {
      if (!current()) return
      try {
        await batchAssignShotTasks(targetProjectId, Number(userId), rows.map(row => ({ shotId: row.shot.shotId, taskLockVersion: row.shot.taskLockVersion })))
        if (!current()) return
        rows.forEach(row => { row.result = '已分配' })
      } catch (error) {
        if (!current()) return
        const status = Number(error?.httpStatus || error?.status)
        rows.forEach(row => { row.result = [400, 401, 403, 404, 409, 422].includes(status) ? '未分配，请刷新核对' : '结果未知，请刷新核对，勿重复分配' })
        const state = shotErrorState(error, '镜头批量分配失败')
        batchAssignError.value = `${state.title}：${state.message}。成功项已生效，其余项未继续执行，请关闭刷新后核对。`
        return
      }
    }
    if (current()) {
      ElMessage.success(`已分配 ${batchAssignForm.rows.length} 个镜头`)
      showBatchAssign.value = false
      const completed = batchAssignForm.rows.map(row => Number(row.shot.shotId))
      resetBatchAssignForm()
      await refreshAfterBatch(completed)
    }
  } finally { assigning.value = false }
}

async function openBatchAssignDialog() {
  if (batchBusy.value || !selectedShots.value.length || selectedShots.value.length > 100 || !selectedShots.value.every(canAssignShot)) return
  resetBatchAssignForm()
  batchAssignProject = currentProjectId.value
  batchAssignGeneration = projectGeneration
  batchAssignForm.rows = selectedShots.value.map(shot => ({ shot: { ...shot }, assigneeUserId: '', result: '未提交' }))
  showBatchAssign.value = true
  await nextTick()
  batchAssignTable.value?.toggleAllSelection()
}

async function closeBatchAssignDialog(force = false) {
  if (assigning.value && !force) return
  const refresh = batchAssignAttempted.value && batchAssignProject === currentProjectId.value && !force
  const completed = batchAssignForm.rows.filter(row => row.result === '已分配').map(row => Number(row.shot.shotId))
  showBatchAssign.value = false
  resetBatchAssignForm()
  if (refresh) await refreshAfterBatch(completed)
}

function resetBatchAssignForm() {
  batchAssignFormRef.value?.clearValidate()
  batchAssignForm.assigneeUserId = ''
  batchAssignForm.rows = []
  batchAssignChecked.value = []
  batchAssignAttempted.value = false
  batchAssignError.value = ''
}

async function openEditDialog(shot, field = '', event = null) {
  if (!canEditShot(shot) || deleting.value || editingShotId.value) return
  const anchor = event?.currentTarget || null
  if (field && !canEditField(shot, field)) return
  const targetProjectId = currentProjectId.value
  const targetShotId = Number(shot.shotId)
  const generation = ++operationGeneration
  editingShotId.value = targetShotId
  try {
    const response = await getShotDetail(targetProjectId, targetShotId)
    if (disposed || currentProjectId.value !== targetProjectId || generation !== operationGeneration) return
    if (Number(response.data?.projectId) !== targetProjectId || Number(response.data?.shotId) !== targetShotId) throw new Error('镜头归属信息已变化，请刷新后重试')
    if (field && !canEditField(response.data, field)) { ElMessage.warning('镜头状态已变化，请刷新后重试'); return }
    editField.value = field
    editAnchor.value = anchor
    editingShot.value = response.data
    editContext.value = Object.freeze({ projectId: targetProjectId, shotId: targetShotId, operationGeneration: generation })
    showEdit.value = true
  } catch (error) {
    if (disposed || currentProjectId.value !== targetProjectId || generation !== operationGeneration) return
    const state = shotErrorState(error, '镜头信息加载失败')
    ElMessage.error(`${state.title}：${state.message}`)
  } finally {
    if (editingShotId.value === targetShotId) editingShotId.value = null
  }
}

function closeEditDialog() {
  const anchor = editAnchor.value
  nextTick(() => { if (anchor?.isConnected) anchor.focus() })
  showEdit.value = false
  editingShot.value = null
  editContext.value = null
  editField.value = ''
  editAnchor.value = null
}

async function handleEdited(_result, operationContext) {
  if (disposed) return
  if (
    editContext.value?.projectId !== Number(operationContext?.projectId) ||
    editContext.value?.shotId !== Number(operationContext?.shotId) ||
    editContext.value?.operationGeneration !== Number(operationContext?.operationGeneration)
  ) {
    notifyDetachedOperation()
    return
  }
  const targetProjectId = editContext.value.projectId
  closeEditDialog()
  if (currentProjectId.value !== targetProjectId) { notifyDetachedOperation(); return }
  ElMessage.success('镜头已更新')
  await loadShots()
}

async function handleEditRefresh() {
  closeEditDialog()
  ElMessage.warning('镜头信息已更新，请从最新列表重新打开')
  await loadShots()
}

async function confirmDeleteShots(targetShots) {
  if (deleting.value || !targetShots.length) return
  const blocked = targetShots.find(shot => !canDeleteShot(shot))
  if (blocked) {
    ElMessage.warning(`${blocked.shotCode} 的任务已经开始，不能删除`)
    return
  }
  const targetProjectId = currentProjectId.value
  const items = targetShots.map(shot => ({ shotId: shot.shotId, lockVersion: shot.lockVersion }))
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${items.length} 个镜头？只有任务未开始的镜头可以删除。`,
      items.length > 1 ? '批量删除镜头' : `删除 ${targetShots[0].shotCode}`,
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
  } catch { return }
  if (currentProjectId.value !== targetProjectId) return
  deleting.value = true
  try {
    await batchDeleteShots(targetProjectId, items)
    ElMessage.success(`已删除 ${items.length} 个镜头`)
    if (currentProjectId.value === targetProjectId) {
      clearShotSelection()
      await loadShots()
    }
  } catch (error) {
    const state = shotErrorState(error, '镜头删除失败')
    ElMessage.error(`${state.title}：${state.message}`)
    if (state.status === 409 && currentProjectId.value === targetProjectId) await loadShots()
  } finally { deleting.value = false }
}

function openCreateDialog() {
  if (!currentProjectId.value) return
  createProjectId.value = currentProjectId.value
  createInitialEpisodeId.value = query.episodeId
  createInitialSceneId.value = query.sceneId
  createOperationGeneration.value = ++operationGeneration
  showCreate.value = true
}

function closeCreateDialog() {
  showCreate.value = false
  createProjectId.value = null
  createInitialEpisodeId.value = ''
  createInitialSceneId.value = ''
  createOperationGeneration.value = null
}

function openImportDialog() {
  if (!currentProjectId.value) return
  importProjectId.value = currentProjectId.value
  importOperationGeneration.value = ++operationGeneration
  showImport.value = true
}

function closeImportDialog() {
  showImport.value = false
  importProjectId.value = null
  importOperationGeneration.value = null
}

function notifyDetachedOperation() {
  ElMessage.success('操作已完成，请切回原项目查看最新结果。')
}

function isActiveOperation(targetProjectId, targetGeneration, operationContext) {
  return (
    targetProjectId === Number(operationContext?.projectId) &&
    targetGeneration === Number(operationContext?.operationGeneration)
  )
}

async function handleSaved(_result, operationContext) {
  if (disposed) return
  const targetProjectId = Number(operationContext?.projectId)
  if (!isActiveOperation(createProjectId.value, createOperationGeneration.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  closeCreateDialog()
  if (currentProjectId.value !== targetProjectId) { notifyDetachedOperation(); return }
  ElMessage.success('镜头已创建')
  await Promise.all([loadShots(), loadEpisodesAfterWrite()])
}

async function loadEpisodesAfterWrite() {
  const projectId = currentProjectId.value
  if (!projectId) return
  episodeRefreshController?.abort()
  const controller = new AbortController()
  episodeRefreshController = controller
  try {
    const rows = await fetchAllPages(
      (params, options) => getEpisodePage(projectId, params, options),
      { lifecycleStatus: 'active', orderByColumn: 'episodeNo', isAsc: 'ascending' },
      controller.signal
    )
    if (episodeRefreshController === controller && currentProjectId.value === projectId) episodes.value = rows
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && currentProjectId.value === projectId) {
      shotsError.value = shotErrorState(error, '集选项刷新失败')
    }
  }
}

async function handleImported(result, operationContext) {
  if (disposed) return
  const targetProjectId = Number(operationContext?.projectId)
  if (!isActiveOperation(importProjectId.value, importOperationGeneration.value, operationContext)) {
    notifyDetachedOperation()
    return
  }
  closeImportDialog()
  if (currentProjectId.value !== targetProjectId) { notifyDetachedOperation(); return }
  ElMessage.success(`镜头导入完成：${result.createdShots} 个新镜头`)
  query.pageNum = 1
  await Promise.all([loadShots(), loadEpisodesAfterWrite()])
}

watch(() => projectContext.projectId, (next, previous) => {
  if (next !== previous) {
    closeShotResults()
    sceneOrderMode.value = false
    closeCreateDialog()
    closeImportDialog()
    closeEditDialog()
    closeSingleAssign()
    closeDetailDrawer()
    closeBatchAssignDialog(true)
    operationGeneration += 1
    query.pageNum = 1
    query.episodeId = sessionStore.workspaceFilters.episodeId
    query.sceneId = sessionStore.workspaceFilters.sceneId
    query.assigneeUserId = sessionStore.workspaceFilters.assigneeUserId
    const saved = sessionStore.shotBrowseState
    if (saved?.projectId === Number(next) && saved.workspaceKey === JSON.stringify(sessionStore.workspaceFilters) && saved.permissionsKey === sessionStore.permissions.join('|')) {
      Object.assign(query, saved.query, { shotStatuses: [...saved.query.shotStatuses] })
      pendingBrowseRestore = saved
    } else pendingBrowseRestore = null
    resetBatchAssignForm()
    loadProjectContext()
  }
})
watch(() => query.sceneId, () => {
  query.shotNoStart = ''
  query.shotNoEnd = ''
  appliedShotRange.value = { shotNoStart: null, shotNoEnd: null }
  shotFilterForm.value?.clearValidate(['shotNoStart', 'shotNoEnd'])
}, { flush: 'sync' })
watch(() => appliedQuery.value, closeSingleAssign)
watch(() => projectContext.scope, () => loadProjects())
watch(viewMode, mode => {
  closeShotResults()
  sceneOrderMode.value = false
  query.pageNum = 1
  if (!['swimlane', 'gantt'].includes(mode)) loadShots()
})

function handleScheduleQueryChange({ mode }) {
  if (['swimlane', 'gantt'].includes(mode)) viewMode.value = mode
}
watch(
  [canDragSort, sceneOrderFullyLoaded, () => shots.value.map(shot => shot.shotId).join(','), () => query.pageNum],
  () => nextTick(initRowSortable),
  { flush: 'post' }
)
onMounted(() => loadProjects(route.query.projectId))
onBeforeUnmount(() => { disposed = true; closeSingleAssign(); destroyRowSortable(); projectController?.abort(); shotController?.abort(); moreController?.abort(); moreObserver?.disconnect(); headerSceneController?.abort(); sceneController?.abort(); episodeRefreshController?.abort() })
</script>

<template>
  <TaskStartDialog v-if="startDialog" :context="startDialog" @close="closeStartDialog" @started="finishStartDialog" @failed="failStartDialog" />
  <ProductionAdjustmentDialog v-if="adjustmentContext" :context="adjustmentContext" @close="closeProductionAdjustment" />
  <BatchShotStartDialog v-if="batchStartContext" :context="batchStartContext" @close="closeBatchStart" />
  <section ref="shotPageRef" class="sg-page shot-page" :class="{ 'shot-page--table': viewMode === 'table', 'shot-page--schedule': ['swimlane', 'gantt'].includes(viewMode) }">
    <header class="sg-page-heading shot-heading">
      <h2 class="sg-page-title">镜头管理</h2>
      <div class="shot-heading__actions"><el-button v-if="canCreateEpisode" @click="openHierarchyCreate('episode')">新建集</el-button><el-button v-if="canCreateScene" :disabled="!episodes.length" @click="openHierarchyCreate('scene')">新建场次</el-button><el-button v-if="canImport" :icon="Upload" @click="openImportDialog">导入 Excel</el-button><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreateDialog">新建镜头</el-button></div>
    </header>
    <TargetPurgeStatus :project-id="currentProjectId" entity-type="shot" :refresh-key="purgeRefresh" />

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <el-form ref="projectContextForm" :model="projectContext" :rules="projectContextRules" class="project-context sg-filter-bar sg-context-bar" size="default" inline label-position="left" aria-label="项目选择">
        <el-form-item label="当前项目"><el-tag>{{ project ? `${project.projectCode} · ${project.projectName}` : projects[0]?.projectName || "加载中" }}</el-tag></el-form-item>
        <div v-if="project" class="project-context__tags"><el-tag size="small" effect="plain" round type="primary">{{ project.projectTypeName }}</el-tag><el-tag size="small" effect="plain" round type="info">{{ project.aspectRatio }}</el-tag><el-tag size="small" effect="plain" round :type="projectRoleMeta(myProjectRoles(project)).type">我的角色：{{ projectRoleMeta(myProjectRoles(project)).label }}</el-tag><el-tag size="small" effect="plain" round :type="tagTypeFromTone(storageMeta(project.storageStatus).tone)">{{ storageMeta(project.storageStatus).label }}</el-tag></div>
      </el-form>

      <el-empty v-if="!projectContext.projectId && !projectsLoading" class="shot-empty" description="当前范围暂无可选项目"><p>请先创建项目，或请项目管理人将你加入项目；如可查看全部项目，也可切换“全部项目”。</p></el-empty>

      <template v-else-if="projectContext.projectId">
        <el-form ref="shotFilterForm" :model="query" :rules="shotFilterRules" class="shot-filters sg-filter-bar" size="default" label-position="top" aria-label="镜头筛选">
          <el-form-item class="shot-filter-item shot-filter-item--keyword" label="镜头搜索" prop="keyword">
            <el-input v-model="query.keyword" class="shot-search" :prefix-icon="Search" maxlength="200" clearable placeholder="镜头号、制作内容、台词或场次名称" aria-label="搜索镜头" />
          </el-form-item>
          <el-form-item class="shot-filter-item" label="集" prop="episodeId">
            <el-select v-model="query.episodeId" placeholder="全部集" aria-label="按集筛选" @change="changeEpisodeFilter"><el-option label="全部集" value="" /><el-option v-for="episode in episodes" :key="episode.episodeId" :label="`${episode.episodeCode} ${episode.episodeName || ''}`" :value="String(episode.episodeId)" /></el-select>
          </el-form-item>
          <el-form-item class="shot-filter-item" label="场次" prop="sceneId">
            <el-select v-model="query.sceneId" :placeholder="scenesLoading ? '加载场次中…' : '全部场次'" aria-label="按场次筛选" :disabled="!query.episodeId || scenesLoading" @change="submitFilters"><el-option :label="scenesLoading ? '加载场次中…' : '全部场次'" value="" /><el-option v-for="scene in scenes" :key="scene.sceneId" :label="`${scene.sceneCode} ${scene.sceneName || ''}`" :value="String(scene.sceneId)" /></el-select>
          </el-form-item>
          <div class="shot-filter-range" role="group" aria-label="镜头号区间">
            <el-form-item class="shot-filter-item" label="起始镜头号" prop="shotNoStart">
              <el-input v-model="query.shotNoStart" :disabled="!query.sceneId" inputmode="numeric" clearable placeholder="起始镜头号" aria-label="起始镜头号" @keyup.enter="submitFilters" />
            </el-form-item>
            <span class="shot-filter-range__separator">至</span>
            <el-form-item class="shot-filter-item" label="结束镜头号" prop="shotNoEnd">
              <el-input v-model="query.shotNoEnd" :disabled="!query.sceneId" inputmode="numeric" clearable placeholder="结束镜头号" aria-label="结束镜头号" @keyup.enter="submitFilters" />
            </el-form-item>
          </div>
          <el-form-item v-if="viewMode !== 'table'" class="shot-filter-item" label="镜头状态" prop="shotStatus">
            <el-select v-model="query.shotStatus" placeholder="全部状态" aria-label="按状态筛选" @change="submitFilters"><el-option label="全部状态" value="" /><el-option v-for="status in ['unassigned','in_progress','reviewing','revision','completed']" :key="status" :label="shotStatusMeta(status).label" :value="status" /></el-select>
          </el-form-item>
          <el-form-item v-if="viewMode !== 'table'" class="shot-filter-item" label="制作人" prop="assigneeUserId">
            <el-select v-model="query.assigneeUserId" placeholder="全部制作人" aria-label="按制作人筛选" @change="submitFilters"><el-option label="全部制作人" value="" /><el-option v-for="member in creatorMembers" :key="member.userId" :label="shotAssigneeOptionLabel(member)" :value="String(member.userId)" /></el-select>
          </el-form-item>
          <el-form-item v-if="!['swimlane', 'gantt'].includes(viewMode)" label="定稿" prop="hasFinal"><el-select v-model="query.hasFinal" aria-label="定稿筛选" @change="submitFilters"><el-option label="全部" value="" /><el-option label="有定稿（含历史）" value="yes" /><el-option label="无定稿" value="no" /></el-select></el-form-item>
          <el-form-item class="shot-filter-actions">
            <el-button type="primary" :icon="Search" :loading="shotsLoading" @click="submitFilters">查询</el-button>
            <el-button :icon="RefreshLeft" :disabled="shotsLoading" @click="resetFilters">重置</el-button>
            <el-button :icon="Refresh" circle aria-label="刷新镜头" :disabled="shotsLoading" @click="loadShots()" />
          </el-form-item>
        </el-form>

        <div class="shot-list-toolbar"><div class="shot-list-toolbar__summary"><strong v-if="['swimlane', 'gantt'].includes(viewMode)">任务排期</strong><strong v-else>{{ total }}</strong><span v-if="!['swimlane', 'gantt'].includes(viewMode)">个镜头<span v-if="shotsLoading"> · 正在刷新</span><span v-else>{{ dragSortHint }}</span></span></div><el-button v-if="shotFeatures.manualSortEnabled && viewMode === 'table' && (canEdit || sceneOrderMode)" size="small" :type="sceneOrderMode ? 'primary' : 'default'" :disabled="shotsLoading || reordering || assigning || deleting || (!sceneOrderMode && (!isSceneOrderScope || total > MAX_SCENE_SORT_SHOTS))" @click="toggleSceneOrderMode">{{ sceneOrderMode ? '退出排序' : '排序模式' }}</el-button><div class="shot-list-toolbar__controls"><el-popover v-if="viewMode === 'table'" placement="bottom-end" :width="280" trigger="click">
          <template #reference><el-button size="small" aria-label="调整镜头行高">行高</el-button></template>
          <el-form ref="rowHeightForm" :model="tableSettings" label-position="top" aria-label="表格行高设置">
            <el-form-item :label="`行高：${tableRowHeight} 像素`" prop="rowHeight"><el-slider v-model="tableRowHeight" :min="72" :max="240" :step="8" aria-label="镜头行高" /></el-form-item>
            <el-button text type="primary" @click="tableRowHeight = 88">恢复默认行高</el-button>
          </el-form>
        </el-popover><el-radio-group :model-value="viewMode" @update:model-value="changeViewMode" class="shot-list-toolbar__views" size="small" aria-label="镜头视图"><el-radio-button value="table"><el-icon><List /></el-icon>表格</el-radio-button><el-radio-button value="storyboard"><el-icon><VideoCamera /></el-icon>故事板</el-radio-button><el-radio-button value="swimlane"><el-icon><Clock /></el-icon>人员任务</el-radio-button><el-radio-button value="gantt"><el-icon><Calendar /></el-icon>制作排期</el-radio-button></el-radio-group></div></div>

        <section v-if="['table', 'storyboard'].includes(viewMode)" class="shot-batch-toolbar" aria-label="镜头批量操作">
          <div class="shot-batch-toolbar__selection">
            <el-tag :type="selectedShots.length ? 'primary' : 'info'" aria-live="polite">已选 {{ selectedShots.length }} 个镜头</el-tag>
            <el-button text :disabled="batchBusy || !selectableShotCount" @click="selectAllShots">全选当前结果</el-button>
            <el-button text :disabled="batchBusy || !selectedShots.length" @click="clearShotSelection">清空选择</el-button>
          </div>
          <div class="shot-batch-toolbar__actions">
            <el-tooltip :content="batchDisabledReason('feedback') || '为选中镜头统一填写反馈，也可逐项补充'" placement="top"><span><el-button type="primary" plain :disabled="Boolean(batchDisabledReason('feedback'))" @click="openDirectFeedback()">批量添加反馈<span v-if="selectedShots.length">（{{ selectedShots.length }}）</span></el-button></span></el-tooltip>
            <el-tooltip :content="batchDisabledReason('schedule') || '统一设置或逐项修改预期制作起止时间'" placement="top"><span><el-button :disabled="Boolean(batchDisabledReason('schedule'))" @click="openBatchStart('schedule')">批量修改周期<span v-if="selectedShots.length">（{{ selectedShots.length }}）</span></el-button></span></el-tooltip>
            <el-tooltip :content="batchDisabledReason('assign') || '统一分配制作人，或逐镜头选择不同制作人'" placement="top"><span><el-button :loading="assigning" :disabled="Boolean(batchDisabledReason('assign'))" @click="openBatchProducer">批量分配制作人<span v-if="selectedShots.length">（{{ selectedShots.length }}）</span></el-button></span></el-tooltip>
            <el-button v-if="selectedShots.length && selectedShots.every(canAdjustShot)" text :disabled="batchBusy || selectedShots.length > 100" @click="openProductionAdjustment(selectedShots)">批量编辑制作任务（{{ selectedShots.length }}）</el-button>
            <el-button v-if="selectedShots.length && canDelete" text type="danger" :disabled="batchBusy || !canDeleteSelection" @click="confirmDeleteShots(selectedShots)">批量删除（{{ selectedShots.length }}）</el-button>
          </div>
          <small class="shot-batch-toolbar__hint">勾选镜头左侧方框，可跨场次多选；每次最多操作 100 个镜头。灰色按钮悬停可查看原因。</small>
        </section>

        <el-alert v-if="pollingError" :title="pollingError" type="warning" show-icon :closable="false" />
        <Suspense v-if="['swimlane', 'gantt'].includes(viewMode) && currentProjectId">
          <ScheduleBoard :project-id="currentProjectId" target-kind="shot" :initial-mode="viewMode" :initial-window-start="sessionStore.workspaceFilters.productionFrom ? `${sessionStore.workspaceFilters.productionFrom}T00:00:00` : ''" :initial-window-end="sessionStore.workspaceFilters.productionTo ? `${sessionStore.workspaceFilters.productionTo}T23:59:59` : ''" :initial-filters="scheduleInitialFilters" :assignee-options="creatorMembers" :editable-allowed="canSchedule" :browse-state="scheduleBrowseState" @remember="scheduleBrowseState = $event" :task-opener="openScheduleResults" :action-loader="loadScheduleActionTarget" :action-factory="scheduleTaskActions" @query-change="handleScheduleQueryChange" />
          <template #fallback><el-card class="shot-loading" shadow="never"><el-skeleton animated :rows="8" /></el-card></template>
        </Suspense>
        <ProjectStatePanel v-else-if="shotsError" :title="shotsError.title" :message="shotsError.message" :retryable="shotsError.retryable" @retry="loadProjectContext" />
        <el-card v-else-if="viewMode !== 'table' && shotsLoading && !shots.length" class="shot-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="8" /></el-card>
        <el-empty v-else-if="viewMode !== 'table' && !shots.length" class="shot-empty" description="当前筛选没有镜头"><p>可以调整集、场次、状态或制作人筛选；项目管理人也可以新建或导入镜头。</p></el-empty>

        <div v-else-if="viewMode === 'table'" class="shot-table-wrap" :style="{ width: `min(100%, ${tableContentWidth}px)` }">
          <el-table @row-contextmenu="(...args) => nasFolderMenu?.open(...args)" ref="shotTableRef" v-loading="shotsLoading" class="shot-data-table" :style="{ '--shot-row-height': `${tableRowHeight}px` }" :data="shots" row-key="shotId" :max-height="shotTableHeight" :row-class-name="({ row }) => Number(row.shotId) === resultsShotId ? 'shot-row--results' : ''" :fit="false" border empty-text="当前筛选没有镜头" @row-click="selectShotResults" @scroll="handleShotTableScroll" @selection-change="handleShotSelectionChange" @header-dragend="saveColumnWidth">
            <template #empty><el-empty class="shot-empty" description="当前筛选没有镜头"><p>可以调整集、场次、状态或制作人筛选；项目管理人也可以新建或导入镜头。</p></el-empty></template>
            <el-table-column type="selection" width="54" fixed="left" align="center" :selectable="isShotSelectable" reserve-selection />
            <el-table-column type="expand" width="40" fixed="left">
              <template #default="{ row }">
                <div class="shot-expanded-details">
                  <div class="shot-detail-panel">
                    <el-descriptions :column="1" :label-width="96" size="small" border>
                      <el-descriptions-item label="制作内容"><div class="shot-detail-text" :class="{ 'shot-detail-empty': !row.description }">{{ row.description || '未填写' }}</div></el-descriptions-item>
                    </el-descriptions>
                    <el-descriptions :column="detailColumnCount" :label-width="96" size="small" border>
                      <el-descriptions-item label="镜头参数"><span :class="{ 'shot-detail-empty': ![row.shotSize, row.cameraPosition, row.cameraMovement, row.focalLength].some(Boolean) }">{{ [row.shotSize, row.cameraPosition, row.cameraMovement, row.focalLength].filter(Boolean).join(' · ') || '未填写' }}</span></el-descriptions-item>
                      <el-descriptions-item v-for="column in shotDetailColumns.filter(item => !['parameters', 'references', 'remark'].includes(item.key))" :key="column.key" :label="column.label"><div class="shot-detail-text" :class="{ 'shot-detail-empty': !row[column.key] }">{{ row[column.key] || '未填写' }}</div></el-descriptions-item>
                    </el-descriptions>
                    <el-descriptions :column="1" :label-width="96" size="small" border>
                      <el-descriptions-item label="备注"><div class="shot-detail-text" :class="{ 'shot-detail-empty': !row.remark }">{{ row.remark || '未填写' }}</div></el-descriptions-item>
                      <el-descriptions-item label="参考内容"><div class="shot-detail-text" v-if="row.referenceDescription">{{ row.referenceDescription }}</div><ReviewReferenceFiles v-if="row.referenceFiles?.length" :files="row.referenceFiles" compact /><span v-else-if="!row.referenceDescription" class="shot-detail-empty">暂无参考内容</span></el-descriptions-item>
                    </el-descriptions>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="镜头" column-key="identity" :width="tableColumnWidths.identity || 132" fixed="left">
              <template #default="{ row }">
                <el-button v-if="hasPermission('shotgrid:shot:query')" class="shot-results-trigger" text :aria-label="`查看镜头成果 ${row.shotCode}`" @click.stop="openShotResults(row, true)"><ProtectedThumbnail class="shot-thumb shot-thumb--small" :thumbnail="row.thumbnail" :alt="`${row.shotCode} 缩略图`" /><FinalVersionTag class="shot-final-position" :row="row" /></el-button>
                <ProtectedThumbnail v-else class="shot-thumb shot-thumb--small" :thumbnail="row.thumbnail" :video="row.proxyMedia" :alt="`${row.shotCode} 缩略图`" />
                <div class="shot-media-links">
                  <el-button link type="primary" :aria-label="`查看镜头 ${row.shotCode}`" @click="openShot(row)">详情</el-button>
                  <el-popover placement="bottom-start" :width="250" trigger="click">
                    <template #reference><el-button link :aria-label="`镜头 ${row.shotCode} 更多`">更多</el-button></template>
                    <ShotActionButtons :actions="moreActions(row)" />
                    <el-button v-if="canEditShot(row) || canAdjustShot(row)" link type="primary" @click="editCell(row, 'references', $event)">编辑参考素材</el-button>
                    <ForceDeleteAction :project-id="currentProjectId" entity-type="shot" :items="[row]" compact @deleted="purgeRefresh++; loadShots()" />
                  </el-popover>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="镜头号" column-key="shotNo" :width="tableColumnWidths.shotNo || 104" fixed="left">
              <template #default="{ row }"><el-button class="shot-cell-editor" text :title="fieldReadOnlyReason(row, 'shotNo')" :aria-label="`编辑镜头号 ${row.shotCode}`" :disabled="!canEditField(row, 'shotNo')" @click="editCell(row, 'shotNo', $event)">{{ row.shotCode }}<el-icon v-if="canEditField(row, 'shotNo')"><Edit /></el-icon></el-button></template>
            </el-table-column>
            <el-table-column label="场次" column-key="scene" :width="tableColumnWidths.scene || 150">
              <template #header><span class="shot-column-heading">场次<el-button text circle size="small" :type="query.sceneId || query.episodeId ? 'primary' : ''" :icon="Filter" aria-label="筛选场次" @click="openHeaderFilter('scene', $event)" /></span></template>
              <template #default="{ row }"><el-button class="shot-cell-editor" text :title="fieldReadOnlyReason(row, 'scene')" :aria-label="`编辑场次 ${row.shotCode}`" :disabled="!canEditField(row, 'scene')" @click="editCell(row, 'scene', $event)"><span>{{ row.episodeCode }} / {{ row.sceneCode }}<small>{{ row.sceneName || '未命名场次' }}</small></span><el-icon v-if="canEditField(row, 'scene')"><Edit /></el-icon></el-button></template>
            </el-table-column>
            <el-table-column label="时长" column-key="duration" :width="tableColumnWidths.duration || 96">
              <template #default="{ row }"><el-button class="shot-cell-editor" text :title="fieldReadOnlyReason(row, 'durationSeconds')" :aria-label="`编辑时长 ${row.shotCode}`" :disabled="!canEditShot(row) && !canAdjustShot(row)" @click="editCell(row, 'durationSeconds', $event)">{{ formatShotDuration(row.durationMs) }}<el-icon v-if="canEditShot(row) || canAdjustShot(row)"><Edit /></el-icon></el-button></template>
            </el-table-column>
            <el-table-column label="制作内容" column-key="description" :width="tableColumnWidths.description || 300">
              <template #default="{ row }"><el-button class="shot-cell-editor shot-cell-editor--content" text :title="fieldReadOnlyReason(row, 'description')" :aria-label="`编辑制作内容 ${row.shotCode}`" :disabled="!canEditShot(row) && !canAdjustShot(row)" @click="editCell(row, 'description', $event)"><span>{{ row.description || '点击填写制作内容' }}</span><el-icon v-if="canEditShot(row) || canAdjustShot(row)"><Edit /></el-icon></el-button></template>
            </el-table-column>
            <el-table-column label="计划时间" column-key="plan" :width="tableColumnWidths.plan || 192">
              <template #header><span class="shot-column-heading">计划时间<el-button text circle size="small" :type="sessionStore.workspaceFilters.productionFrom ? 'primary' : ''" :icon="Filter" aria-label="筛选计划时间" @click="openHeaderFilter('plan', $event)" /></span></template>
              <template #default="{ row }"><el-button class="shot-cell-editor" text :aria-label="`编辑计划时间 ${row.shotCode}`" :disabled="!canScheduleShot(row)" :title="canScheduleShot(row) ? '设置或调整预期制作时间' : !row.taskId ? '分配制作人后可设置排期' : '当前阶段或权限不允许调整排期'" @click="openBatchStart('schedule', [row], true)"><div class="shot-plan"><span><small>起</small> <span class="task-date-cell task-expected-start">{{ formatTaskDateTime(row.expectedStartTime) }}</span></span><span><small>止</small> <span class="task-date-cell task-expected-end">{{ formatTaskDateTime(row.expectedEndTime) }}</span></span><small v-if="!row.expectedStartTime">{{ row.taskId ? '点击设置排期' : '待分配制作人' }}</small></div><el-icon v-if="canScheduleShot(row)"><Edit /></el-icon></el-button><div class="task-time-state"><el-tag v-if="row.status !== 'completed'" size="small" :type="tagTypeFromTone(shotTimeState(row).tone)">{{ shotTimeState(row).label }}</el-tag></div></template>
            </el-table-column>
            <el-table-column label="制作人" column-key="assignee" :width="tableColumnWidths.assignee || 140">
              <template #header><span class="shot-column-heading">制作人<el-button text circle size="small" :type="query.assigneeUserId ? 'primary' : ''" :icon="Filter" aria-label="筛选制作人" @click="openHeaderFilter('assignee', $event)" /></span></template>
              <template #default="{ row }"><el-button class="shot-cell-editor" text :aria-label="`编辑制作人 ${row.shotCode}`" :disabled="!canOpenShotAssign(row) && !canAdjustShot(row)" :title="canOpenShotAssign(row) || canAdjustShot(row) ? '选择制作人' : row.status === 'pending_info' ? '请先填写制作内容' : '当前阶段或权限不允许改派'" @click="editProducer(row)"><span>{{ row.assignee ? shotAssigneeName(row.assignee, members) : '点击分配' }}<small v-if="row.previousAssigneeNames?.length">原：{{ row.previousAssigneeNames.join('、') }}</small></span><el-icon v-if="canOpenShotAssign(row) || canAdjustShot(row)"><Edit /></el-icon></el-button></template>
            </el-table-column>
            <el-table-column label="镜头状态" column-key="status" :width="tableColumnWidths.status || 150">
              <template #header><span class="shot-column-heading">镜头状态<el-button text circle size="small" :type="query.shotStatuses.length || query.shotStatus ? 'primary' : ''" :icon="Filter" aria-label="筛选镜头状态" @click="openHeaderFilter('status', $event)" /></span></template>
              <template #default="{ row }">
                <el-popover placement="bottom-end" :width="260" trigger="click">
                  <template #reference><el-button text class="shot-cell-editor" :aria-label="`镜头状态操作 ${row.shotCode}`"><el-tag :class="shotStatusTagClass(row)" :type="tagTypeFromTone(shotStatusMeta(row).tone)" size="small" round>{{ shotStatusMeta(row).label }}</el-tag><span aria-hidden="true">⌄</span></el-button></template>
                  <p class="shot-status-help">{{ shotStatusMeta(row).label }} · 选择下一步操作</p>
                  <ShotActionButtons v-if="statusActions(row).length" :actions="statusActions(row)" />
                  <el-empty v-else :image-size="36" :description="row.status === 'unassigned' ? '请在制作人栏分配任务' : '当前没有可执行的状态操作'" />
                </el-popover>
                <el-tag v-if="row.directoryStatus === 'failed'" type="danger" size="small">目录准备失败</el-tag>
              </template>
            </el-table-column>
            <el-table-column v-for="column in shotDetailColumns.filter(item => visibleDetailColumns.includes(item.key))" :key="column.key" :column-key="column.key" :label="column.label" :width="tableColumnWidths[column.key] || column.width">
              <template #default="{ row }"><el-button class="shot-cell-editor shot-cell-editor--content" text :aria-label="`编辑${column.label} ${row.shotCode}`" :disabled="!canEditShot(row) && !canAdjustShot(row)" @click="editCell(row, column.key, $event)"><span>{{ column.key === 'parameters' ? [row.shotSize, row.cameraPosition, row.cameraMovement, row.focalLength].filter(Boolean).join(' · ') || '点击填写' : column.key === 'references' ? row.referenceDescription || '查看 / 编辑参考内容' : row[column.key] || '点击填写' }}</span><el-icon v-if="canEditShot(row) || canAdjustShot(row)"><Edit /></el-icon></el-button></template>
            </el-table-column>
            <el-table-column column-key="addColumn" width="104" fixed="right">
              <template #header><el-popover placement="bottom-end" :width="280" trigger="click">
          <template #reference><el-button size="small" :icon="Plus" aria-label="添加表格列">添加列</el-button></template>
          <el-form ref="columnSettingsFormRef" label-position="top" :model="tableSettings" class="shot-column-settings">
            <el-form-item label="显示方式" prop="mode"><el-select v-model="tablePresentationMode" aria-label="表格显示方式"><el-option label="基础列" value="auto" /><el-option label="精简列" value="compact" /><el-option label="完整列" value="full" /><el-option label="自定义列" value="custom" /></el-select></el-form-item>
            <el-form-item label="附加信息列"><el-checkbox-group :model-value="visibleDetailColumns" @update:model-value="setDetailColumns"><el-checkbox v-for="column in shotDetailColumns" :key="column.key" :value="column.key">{{ column.label }}</el-checkbox></el-checkbox-group></el-form-item>
            <p>收起的信息仍可在行首展开查看。拖动表头边界可调整列宽。</p>
            <el-button text type="primary" @click="resetTablePresentation">恢复默认布局</el-button>
          </el-form>
        </el-popover></template>
              <template #default><span /></template>
            </el-table-column>
          </el-table>
        </div>

        <section v-else class="storyboard" :class="[`storyboard--${storyboardSize}`, { 'is-refreshing': shotsLoading }]">
          <div class="storyboard__tools">
            <el-text size="small">按场次查看 · 点击镜头查看成果与反馈</el-text>
            <el-radio-group v-model="storyboardSize" size="small" aria-label="故事板缩略图大小"><el-radio-button value="small">小图</el-radio-button><el-radio-button value="medium">中图</el-radio-button><el-radio-button value="large">大图</el-radio-button></el-radio-group>
          </div>
          <el-collapse v-model="expandedScenes">
            <el-collapse-item v-for="group in storyboardGroups" :key="group.key" :name="group.key" :title="`${group.label} · ${group.shots.length} 个镜头`">
              <el-checkbox-group v-if="expandedScenes.includes(group.key)" v-model="storyboardSelection" class="storyboard__grid" aria-label="选择镜头">
                <el-card v-for="shot in group.shots" :key="shot.shotId" class="story-frame" :class="{ 'is-active': resultsShotId === Number(shot.shotId) }" shadow="hover" @click="selectShotResults(shot, null, $event)">
                  <div class="story-frame__media">
                    <el-button class="story-preview-button" text :disabled="!hasPermission('shotgrid:shot:query')" :aria-label="`预览镜头成果 ${shot.shotCode}`" @click.stop="openShotResults(shot, true)"><ProtectedThumbnail class="shot-thumb" :thumbnail="shot.thumbnail" :video="shot.proxyMedia" :alt="`${shot.shotCode} 缩略图`" /></el-button><FinalVersionTag :row="shot" />
                  </div>
                  <div class="story-frame__content">
                    <header class="story-frame__heading">
                      <el-checkbox :value="Number(shot.shotId)" :disabled="batchBusy || !canSelectShot(shot)" :aria-label="`选择镜头 ${shot.shotCode}`" />
                      <h3><el-button link type="primary" @click="openShotResults(shot)">{{ shot.episodeCode }} / {{ shot.sceneCode }} / {{ shot.shotCode }}</el-button></h3>
                      <el-tag class="shot-status-tag" :class="shotStatusTagClass(shot)" :type="tagTypeFromTone(shotStatusMeta(shot).tone)" size="small" effect="light" round>{{ shotStatusMeta(shot).label }}</el-tag>
                    </header>
                    <div class="story-frame__description" :title="shot.description">{{ shot.description || '暂未填写制作内容' }}</div>
                    <div class="story-frame__summary"><span>{{ formatShotDuration(shot.durationMs) }}</span><span>{{ shotAssigneeName(shot.assignee, members) }}</span></div>
                    <TaskFeedbackShortcut v-if="shot.taskId" :task-id="Number(shot.taskId)" :enabled="Boolean(shot.latestVersion) && hasPermission('shotgrid:note:list') && canViewTask(shot)" :refresh-key="`${shot.latestVersion?.versionId}:${shot.taskLockVersion}`" @open="openShotResults(shot)" />
                    <ShotActionButtons class="story-frame__actions" :actions="shotActions(shot)">
                      <ForceDeleteAction :project-id="currentProjectId" entity-type="shot" :items="[shot]" compact @deleted="purgeRefresh++; loadShots()" />
                    </ShotActionButtons>
                  </div>
                </el-card>
              </el-checkbox-group>
            </el-collapse-item>
          </el-collapse>
        </section>

        <div v-if="!['swimlane', 'gantt'].includes(viewMode) && shots.length && hasNext && !sceneOrderMode" ref="loadMoreRef" class="shot-load-more" aria-live="polite">
          <span>已加载 {{ shots.length }} / {{ total }} 个镜头，向下滚动继续查看</span>
          <el-alert v-if="moreError" :title="moreError" type="error" :closable="false" show-icon />
          <el-button :loading="loadingMore" :disabled="shotsLoading || refreshingShots" @click="loadMoreShots">{{ moreError ? '重试加载' : '加载更多镜头' }}</el-button>
        </div>
      </template>
    </template>

    <ShotFormDialog v-if="showCreate && createProjectId && createOperationGeneration" :project-id="createProjectId" :operation-generation="createOperationGeneration" :episodes="episodes" :initial-episode-id="createInitialEpisodeId" :initial-scene-id="createInitialSceneId" @close="closeCreateDialog" @saved="handleSaved" @refresh="loadProjectContext" />
    <el-popover :visible="Boolean(showEdit && editAnchor)" :virtual-ref="editAnchor" virtual-triggering placement="bottom-start" :width="420" :persistent="false" popper-class="shot-inline-editor">
      <ShotFormDialog v-if="showEdit && editAnchor && editContext && editingShot" :key="`${editContext.shotId}:${editField}`" embedded :field="editField" :project-id="editContext.projectId" :operation-generation="editContext.operationGeneration" :episodes="episodes" :shot="editingShot" @close="closeEditDialog" @saved="handleEdited" @refresh="handleEditRefresh" />
    </el-popover>
    <el-popover :visible="Boolean(headerFilterKind)" :virtual-ref="headerFilterAnchor" virtual-triggering placement="bottom-end" :width="360" :persistent="false">
      <el-form v-if="headerFilterKind" ref="headerFilterForm" :model="headerFilterDraft" :rules="headerFilterRules" label-position="top" aria-label="表头筛选表单">
        <template v-if="headerFilterKind === 'scene'">
          <el-form-item label="集" prop="episodeId"><el-select v-model="headerFilterDraft.episodeId" filterable clearable placeholder="全部集" aria-label="表头筛选集" @change="loadHeaderScenes()"><el-option v-for="episode in episodes" :key="episode.episodeId" :label="`${episode.episodeCode} ${episode.episodeName || ''}`" :value="String(episode.episodeId)" /></el-select></el-form-item>
          <el-form-item label="场次" prop="sceneId"><el-select v-model="headerFilterDraft.sceneId" filterable clearable :loading="headerScenesLoading" :disabled="!headerFilterDraft.episodeId || headerScenesLoading || Boolean(headerScenesError)" :placeholder="headerFilterDraft.episodeId ? '全部场次' : '请先选择集'" aria-label="表头筛选场次"><el-option v-for="scene in headerScenes" :key="scene.sceneId" :label="`${scene.sceneCode} ${scene.sceneName || ''}`" :value="String(scene.sceneId)" /></el-select></el-form-item>
          <el-alert v-if="headerScenesError" :title="headerScenesError" type="error" :closable="false"><el-button text type="primary" @click="loadHeaderScenes(false)">重试</el-button></el-alert>
        </template>
        <el-form-item v-if="headerFilterKind === 'assignee'" label="筛选制作人" prop="assigneeUserId"><el-select v-model="headerFilterDraft.assigneeUserId" filterable clearable placeholder="全部制作人"><el-option v-for="member in creatorMembers" :key="member.userId" :label="shotAssigneeOptionLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
        <el-form-item v-if="headerFilterKind === 'plan'" label="预期制作时间（范围有交集）" prop="dates"><el-date-picker v-model="headerFilterDraft.dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" unlink-panels /></el-form-item>
        <el-form-item v-if="headerFilterKind === 'status'" label="筛选镜头状态" prop="statuses"><el-select v-model="headerFilterDraft.statuses" multiple clearable placeholder="全部状态"><el-option v-for="status in shotStatusOptions" :key="status" :label="shotStatusMeta(status).label" :value="status" /></el-select></el-form-item>
        <el-form-item><el-button type="primary" :loading="shotsLoading" :disabled="headerScenesLoading || headerFilterKind === 'scene' && Boolean(headerScenesError)" @click="applyHeaderFilter">应用</el-button><el-button :disabled="shotsLoading" @click="resetHeaderFilter">清除</el-button><el-button @click="headerFilterKind = ''">取消</el-button></el-form-item>
      </el-form>
    </el-popover>
    <ShotFormDialog v-if="showEdit && !editAnchor && editContext && editingShot" :project-id="editContext.projectId" :operation-generation="editContext.operationGeneration" :episodes="episodes" :shot="editingShot" @close="closeEditDialog" @saved="handleEdited" @refresh="handleEditRefresh" />
    <ShotAssignDialog v-if="singleAssignContext" :key="singleAssignContext.operationGeneration" :project-id="singleAssignContext.projectId" :operation-generation="singleAssignContext.operationGeneration" :shot="singleAssignContext.shot" :members="members" @close="closeSingleAssign" @assigned="handleSingleAssigned" @refresh="refreshSingleAssign" />
    <ShotImportDialog v-if="showImport && importProjectId && importOperationGeneration" :project-id="importProjectId" :operation-generation="importOperationGeneration" :project-name="project?.projectName" @close="closeImportDialog" @imported="handleImported" />
    <EpisodeSceneCreateDialog v-if="showHierarchyCreate && currentProjectId" :project-id="currentProjectId" :mode="hierarchyCreateMode" :episodes="episodes" :initial-episode-id="query.episodeId" @close="closeHierarchyCreate" @saved="handleHierarchySaved" />
    <el-drawer v-model="showBatchAssign" class="shot-batch-assign-drawer" :title="batchAssignLabel" size="min(1040px, 95vw)" direction="rtl" append-to-body :close-on-click-modal="!assigning" :close-on-press-escape="!assigning" :show-close="!assigning" @close="closeBatchAssignDialog()">
      <el-form ref="batchAssignFormRef" :model="batchAssignForm" :rules="batchAssignRules" class="batch-assign-form" label-position="top" aria-label="镜头批量分配表单" :disabled="assigning || batchAssignAttempted">
        <div class="batch-assign-summary"><strong>共 {{ batchAssignForm.rows.length }} 个镜头待核对</strong><span>先批量指定制作人，再逐项微调，确认后生效。</span></div>
        <div class="batch-assign-toolbar">
          <div class="batch-assign-toolbar__label"><strong>批量设置</strong><span>已勾选 {{ batchAssignChecked.length }} 项</span></div>
          <el-form-item prop="assigneeUserId"><el-select popper-class="batch-assign-member-options" v-model="batchAssignForm.assigneeUserId" filterable clearable placeholder="选择制作人" aria-label="批量分配制作人"><el-option v-for="member in creatorMembers" :key="member.userId" :label="shotAssigneeOptionLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
          <el-button type="primary" :disabled="!batchAssignChecked.length" @click="applyBatchAssignee">应用到勾选项</el-button>
        </div>
        <div class="batch-assign-table-heading"><strong>逐项核对</strong><span>可在右侧单独调整制作人</span></div>
        <el-table class="batch-assign-table" ref="batchAssignTable" :data="batchAssignForm.rows" :row-key="row => row.shot.shotId" height="100%" @selection-change="value => batchAssignChecked = value">
          <el-table-column type="selection" width="44" :selectable="() => !assigning && !batchAssignAttempted" />
          <el-table-column label="镜头" width="200"><template #default="{ row }">{{ [row.shot.episodeCode, row.shot.sceneCode, row.shot.shotCode].join(' / ') }}</template></el-table-column>
          <el-table-column label="制作内容" min-width="280" show-overflow-tooltip><template #default="{ row }">{{ row.shot.description || '未填写' }}</template></el-table-column>
          <el-table-column label="拟分配制作人" width="240"><template #default="{ row, $index }">
            <el-form-item :prop="`rows.${$index}.assigneeUserId`" :rules="batchAssigneeRules"><el-select popper-class="batch-assign-member-options" v-model="row.assigneeUserId" filterable clearable :aria-label="`${row.shot.shotCode} 拟分配制作人`" placeholder="请选择制作人"><el-option v-for="member in creatorMembers" :key="member.userId" :label="shotAssigneeOptionLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
            <small v-if="row.shot.assignee" class="batch-assign-current">当前：{{ shotAssigneeName(row.shot.assignee, members) }}</small>
          </template></el-table-column>
          <el-table-column v-if="batchAssignAttempted" label="执行结果" prop="result" min-width="150" />
        </el-table>
        <div class="batch-assign-counts" aria-label="分配汇总"><strong>分配汇总</strong><div class="batch-assign-counts__tags"><el-tag v-for="group in batchAssignCounts" :key="group.id" :type="group.id ? 'info' : 'warning'" effect="plain">{{ group.name }} {{ group.count }} 项</el-tag></div></div>
      </el-form>
      <el-alert v-if="batchAssignError" :title="batchAssignError" type="error" show-icon :closable="false" />
      <template #footer><el-button :disabled="assigning" @click="closeBatchAssignDialog()">{{ batchAssignAttempted ? '关闭并刷新' : '取消' }}</el-button><el-button type="primary" :loading="assigning" :disabled="assigning || batchAssignAttempted" @click="confirmBatchAssign">确认{{ hasAssignedSelection ? '重新分配' : '分配' }}</el-button></template>
    </el-drawer>
    <el-drawer v-model="showDetail" class="sg-detail-drawer shot-detail-drawer" modal-class="sg-detail-drawer-mask" header-class="sg-detail-drawer__header" body-class="sg-detail-drawer__body" :title="detailDrawerTitle" direction="rtl" size="85%" resizable append-to-body destroy-on-close @closed="clearDetailDrawer">
      <ShotDetailView v-if="detailShotId && currentProjectId" embedded :target-project-id="currentProjectId" :target-shot-id="detailShotId" @changed="handleDetailChanged" @deleted="handleDetailDeleted" />
    </el-drawer>
    <ShotTaskFeedbackDialog :key="currentProjectId" ref="directFeedbackDialog" @active-change="value => { directFeedbackOpen = value }" @closed="closeDirectFeedback" />
    <RelatedDetailDrawer ref="workDrawer" @closed="handleWorkDrawerClosed" />
  </section>
  <NasFolderMenu ref="nasFolderMenu" :project-id="Number(currentProjectId) || 0" :can-query="hasPermission('shotgrid:version:query')" />

  <ResultsDrawer :model-value="Boolean(resultsShotId)" title="镜头" :modal="false" modal-penetrable :lock-scroll="false" :close-on-click-modal="false" aria-modal="false" modal-class="shot-results-drawer" append-to-body destroy-on-close :before-close="beforeCloseResults">
    <template #header><div class="shot-results-navigation"><strong>镜头</strong><el-button size="small" :disabled="batchBusy || shotsLoading || resultsIndex <= 0" @click="moveShotResults(-1)">上一镜头</el-button><el-button size="small" :disabled="batchBusy || shotsLoading || resultsIndex < 0 || resultsIndex >= shots.length - 1" @click="moveShotResults(1)">下一镜头</el-button><el-text size="small" type="info">↑ ↓ 快速切换</el-text></div></template>
    <ShotResultsPanel v-if="resultsShotId && currentProjectId" ref="resultsPanel" :key="`${currentProjectId}:${resultsShotId}`" :project-id="currentProjectId" :shot-id="resultsShotId" :preview-on-load="resultsPreview" @updated="refreshAfterBatch([])" />
  </ResultsDrawer>
</template>

<style scoped>
.story-preview-button { display: block; width: 100%; height: auto; padding: 0; }
.story-preview-button :deep(> span) { display: block; width: 100%; }
.story-frame__media { position: relative; }
.story-frame__media > .final-version-tag { position: absolute; top: 5px; right: 5px; max-width: calc(100% - 10px); pointer-events: none; }

.shot-results-trigger { position: relative; }
.shot-final-position { position: absolute; top: 0; right: 0; font-size: 10px; }
.shot-batch-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;padding:10px 12px;margin-bottom:10px;border:1px solid var(--sg-border);border-radius:8px;background:var(--sg-surface)}
.shot-batch-toolbar__selection,.shot-batch-toolbar__actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.shot-batch-toolbar .el-button{margin-left:0}.shot-batch-toolbar__hint{flex-basis:100%;color:var(--sg-text-muted);font-size:12px}
.shot-data-table :deep(.el-table-column--selection .el-checkbox__inner){width:17px;height:17px;border-color:var(--sg-text-muted)}
.shot-data-table :deep(.el-table-column--selection .is-indeterminate .el-checkbox__inner::before){top:calc(50% - 1px)}

.shot-results-trigger { padding: 0; height: auto; width: 100%; justify-content: flex-start; }
.shot-results-navigation { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.shot-results-navigation .el-button { margin-left: 0; }
.shot-results-trigger :deep(> span) { display: block; width: 100%; }
/* 行高统一调整；表格、列宽拖动及滚动仍使用 Element Plus 的原生契约。 */
.shot-data-table :deep(.el-table__row > td.el-table__cell) { height: var(--shot-row-height); padding: 6px 0; box-sizing: border-box; }
.shot-data-table :deep(.el-table__row > td.el-table__cell > .cell) { max-height: calc(var(--shot-row-height) - 12px); overflow: hidden; }
.shot-data-table :deep(th.el-table__cell) { padding: 5px 0; }
.shot-data-table :deep(th.el-table__cell:not(:last-child)) { border-right-color: var(--sg-border-strong); }
.shot-data-table .shot-thumb--small { width: min(80px, 100%); height: 44px; border-radius: 6px; }
.shot-data-table .shot-media-links { margin-top: 3px; }
.shot-data-table .shot-cell-editor { min-height: 28px; padding: 2px; }
.shot-data-table .shot-cell-editor--content :deep(> span > span) { display: block; max-height: calc(var(--shot-row-height) - 20px); overflow: hidden; }
.shot-plan { display: grid; gap: 2px; }
.shot-plan > span { display: flex; gap: 6px; align-items: baseline; }
.shot-plan small { display: inline; line-height: 1.2; }
.shot-load-more { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 8px 16px; padding: 10px; color: var(--sg-text-muted); font-size: 12px; }
.shot-load-more .el-alert { flex-basis: 100%; }
.shot-list-toolbar > .shot-list-toolbar__controls { margin-left: auto; padding: 0; border: 0; background: transparent; }
:global(.shot-inline-editor) { max-width: calc(100vw - 24px); }
.shot-column-heading { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
.shot-media-links { display: flex; gap: 8px; margin-top: 5px; }
.shot-cell-editor { width: 100%; height: auto; min-height: 38px; margin: 0; padding: 6px; justify-content: flex-start; white-space: normal; text-align: left; }
.shot-cell-editor :deep(> span) { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 6px; min-width: 0; }
.shot-cell-editor small { display: block; color: var(--sg-text-muted); font-size: 11px; line-height: 1.6; }
.shot-cell-editor .el-icon { flex: 0 0 auto; font-size: 12px; color: var(--sg-text-muted); }
.shot-cell-editor.is-disabled { cursor: default; color: var(--sg-text-secondary); }
.shot-cell-editor--content :deep(> span > span) { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; line-height: 1.7; }
.shot-status-help { margin: 0 0 12px; color: var(--sg-text-secondary); }

.shot-data-table :deep(td.el-table__expanded-cell) { padding: 0; background: var(--sg-surface-soft); }
.shot-expanded-details { padding: 12px 16px; font-size: 12px; --el-descriptions-table-border: 1px solid var(--sg-border); }
.shot-detail-panel { overflow: hidden; background: var(--sg-surface); border: 1px solid var(--sg-border); border-radius: 8px; }
.shot-detail-panel :deep(.el-descriptions + .el-descriptions) { margin-top: -1px; }
.shot-expanded-details :deep(.el-descriptions__body) { background: var(--sg-surface); }
.shot-expanded-details :deep(.el-descriptions__table) { table-layout: fixed; }
.shot-expanded-details :deep(.el-descriptions__table.is-bordered .el-descriptions__cell) { padding: 8px 12px; font-size: 12px; line-height: 1.6; vertical-align: top; }
.shot-expanded-details :deep(.el-descriptions__label) { white-space: nowrap; color: var(--sg-text-muted); background: var(--sg-surface-soft); font-weight: 500; }
.shot-expanded-details :deep(.el-descriptions__content) { color: var(--sg-text-secondary); overflow-wrap: anywhere; }
.shot-detail-empty { color: var(--sg-text-muted); }
.shot-expanded-details .shot-detail-text { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 700px) {
  .shot-expanded-details { padding: 8px; }
  .shot-expanded-details :deep(.el-descriptions__table.is-bordered .el-descriptions__cell) { padding: 6px 8px; }
}

.shot-card__media{position:relative}
.shot-directory-status{height:16px;padding:0 5px;font-size:10px;line-height:1}
.shot-list-toolbar>.shot-list-toolbar__summary{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:0;background:transparent;border:0}.shot-list-toolbar__summary>strong{color:var(--sg-text);font-size:23px;line-height:1}.shot-list-toolbar__summary>span{color:var(--sg-text-muted);font-size:11px}.shot-list-toolbar__summary:deep(.el-button){margin-left:0}.batch-assign-summary{display:grid;gap:6px;margin-bottom:20px;padding:14px;color:var(--sg-text-secondary);background:var(--sg-accent-soft);border-radius:10px}.batch-assign-summary strong{color:var(--sg-text)}.batch-assign-summary span{font-size:12px;line-height:1.5}.batch-assign-form:deep(.el-form-item){margin-bottom:0}.batch-assign-form:deep(.el-select){width:100%}.shot-selection{width:15px;height:15px;cursor:pointer}.shot-selection:disabled{cursor:not-allowed;opacity:.35}.shot-row-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.shot-long-text{line-height:1.55;white-space:pre-wrap}.shot-identity strong,.shot-identity small,.shot-parameters span,.shot-parameters small{display:block}.shot-identity small,.shot-parameters small{margin-top:5px;color:var(--sg-text-muted)}.shot-assets{display:flex;gap:5px;align-items:flex-start;flex-direction:column}.shot-assets__empty{color:var(--sg-text-muted)}.shot-status{display:grid;gap:5px;justify-items:start}
.shot-page{position:relative;padding-inline:16px}.shot-heading__actions{display:flex;gap:10px}.project-context{display:flex;gap:16px;align-items:end;margin-bottom:14px;padding:16px;background:linear-gradient(90deg,rgba(255,182,87,.06),transparent),var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.project-context label{display:grid;min-width:280px;gap:6px}.project-context label>span{color:var(--sg-text-muted);font-size:10px}select,input{color:var(--sg-text);background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:9px}select{height:40px;padding:0 10px}.shot-filters{display:grid;grid-template-columns:minmax(240px,1.6fr) repeat(4,minmax(130px,.7fr)) auto auto;gap:9px;margin-bottom:14px;padding:14px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.shot-search{display:flex;height:40px;gap:8px;align-items:center;padding:0 11px;background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:9px}.shot-search input{min-width:0;flex:1;background:transparent;border:0;outline:0}.shot-list-toolbar{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:0 2px 12px;color:var(--sg-text-muted);font-size:12px}.shot-list-toolbar>div{display:flex;gap:5px;padding:4px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:9px}.shot-list-toolbar button{display:flex;gap:5px;align-items:center;padding:7px 9px;color:var(--sg-text-muted);cursor:pointer;background:transparent;border:0;border-radius:6px}.shot-list-toolbar button.active{color:var(--sg-accent);background:var(--sg-accent-soft)}.shot-loading,.shot-empty{display:grid;min-height:320px;place-items:center;align-content:center;padding:30px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg)}.shot-empty>.el-icon{color:var(--sg-accent);font-size:34px}.shot-empty h3,.shot-empty p{margin:12px 0 0}.shot-empty p{max-width:600px;font-size:12px;text-align:center}.shot-table-wrap{overflow:hidden;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.shot-data-table{--el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);--el-table-border-color:var(--sg-border);width:100%}.shot-data-table:deep(.el-table__cell){padding:12px 0;font-size:11px}.shot-data-table:deep(th.el-table__cell){font-weight:650}.shot-description{line-height:1.55}.feedback-cell{line-height:1.55}.shot-thumb{position:relative;overflow:hidden;aspect-ratio:16/9;background:var(--sg-surface-soft);border-radius:10px}.shot-thumb img{width:100%;height:100%;object-fit:cover}.shot-thumb>div{display:grid;width:100%;height:100%;gap:5px;color:var(--sg-text-muted);place-items:center;align-content:center}.shot-thumb--small{width:90px}.shot-thumb--small>.el-icon{position:absolute;top:50%;left:50%;color:var(--sg-text-muted);font-size:20px;transform:translate(-50%,-50%)}.shot-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:15px}.shot-card{padding:12px;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:transform .15s,border-color .15s}.shot-card:hover,.shot-card:focus-visible,.story-frame:hover,.story-frame:focus-visible{border-color:rgba(255,182,87,.35);outline:0;transform:translateY(-2px)}.shot-card__duration{position:absolute;right:8px;bottom:8px;padding:4px 6px;color:white;font-size:10px;background:rgba(0,0,0,.72);border-radius:5px}.shot-card header,.shot-card footer{display:flex;gap:10px;align-items:center;justify-content:space-between}.shot-card header{margin-top:13px}.shot-card h3,.shot-card small,.shot-card p{margin:0}.shot-card h3{margin-top:3px;font-size:18px}.shot-card small,.shot-card footer{color:var(--sg-text-muted);font-size:10px}.shot-card>p{min-height:44px;margin:11px 0;color:var(--sg-text-secondary);font-size:12px;line-height:1.55}.storyboard{display:grid;gap:10px}.story-frame{display:grid;grid-template-columns:45px 230px 1fr;gap:14px;align-items:center;padding:10px;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:transform .15s,border-color .15s}.story-frame__index{color:var(--sg-accent);font-size:12px;font-weight:800;text-align:center}.story-frame p{margin:7px 0;color:var(--sg-text-secondary);font-size:12px}.story-frame small{color:var(--sg-text-muted)}.is-refreshing{opacity:.55}@media(max-width:1480px){.shot-filters{grid-template-columns:repeat(3,minmax(0,1fr))}.shot-search{grid-column:span 2}.project-context{align-items:stretch;flex-direction:column}}@media(max-width:760px){.shot-filters{grid-template-columns:1fr}.shot-search{grid-column:auto}.story-frame{grid-template-columns:35px 120px 1fr}.project-context label{min-width:0}}
.shot-list-toolbar>.shot-list-toolbar__summary{gap:8px;padding:0;background:transparent;border:0;border-radius:0}.shot-list-toolbar>.shot-list-toolbar__summary .el-button{margin-left:0;padding:8px 15px;color:inherit;background:transparent;border-radius:4px}.shot-list-toolbar>.shot-list-toolbar__summary .el-button--primary{color:var(--el-color-primary)}.shot-list-toolbar>.shot-list-toolbar__summary .el-button--danger{color:var(--el-color-danger)}
.project-context:deep(.el-form-item){min-width:280px;margin:0;align-items:center}.project-context:deep(.el-form-item__label){height:32px;padding:0 8px 0 0;align-items:center;color:var(--sg-text-muted);font-size:12px;line-height:32px}.shot-filters .shot-search{height:auto;padding:0;background:transparent;border:0}.shot-list-toolbar__views{padding:0!important;background:transparent!important}.shot-list-toolbar__views:deep(.el-radio-button__inner){display:flex;gap:6px;align-items:center;color:var(--sg-text-muted);background:var(--sg-surface);border-color:var(--sg-border);box-shadow:none}.shot-list-toolbar__views:deep(.el-radio-button__original-radio:checked+.el-radio-button__inner){color:var(--sg-accent);background:var(--sg-accent-soft);border-color:rgba(255,182,87,.32);box-shadow:-1px 0 0 0 rgba(255,182,87,.32)}.shot-card{padding:0}.shot-card:deep(.el-card__body){padding:12px}.shot-card:deep(.el-card__body)>p{min-height:44px;margin:11px 0;color:var(--sg-text-secondary);font-size:12px;line-height:1.55}.story-frame{display:block;padding:0}.story-frame:deep(.el-card__body){display:grid;grid-template-columns:45px 230px minmax(0,1fr);gap:14px;align-items:center;padding:10px}@media(max-width:760px){.story-frame:deep(.el-card__body){grid-template-columns:35px 120px minmax(0,1fr)}}
.shot-filters{align-items:start;grid-template-columns:minmax(200px,1.4fr) repeat(2,minmax(100px,.65fr)) minmax(240px,1.3fr) repeat(3,minmax(100px,.65fr)) auto}
.shot-filter-range{display:flex;gap:6px;align-items:flex-start;min-width:0}.shot-filter-range>.shot-filter-item{flex:1;min-width:0}.shot-filter-range__separator{line-height:32px;color:var(--sg-text-muted)}
.shot-filters:deep(.el-form-item){min-width:0;margin-bottom:0}
.shot-filter-item:deep(.el-form-item__content),.shot-filter-item:deep(.el-select),.shot-filter-item:deep(.el-input){width:100%;min-width:0}
.shot-filter-actions:deep(.el-form-item__content){flex-wrap:nowrap;justify-content:flex-end}
@media(max-width:1480px){.shot-filters{grid-template-columns:repeat(3,minmax(0,1fr))}.shot-filter-item--keyword{grid-column:span 2}.shot-filter-actions:deep(.el-form-item__content){justify-content:flex-start}}
@media(max-width:760px){.shot-filters{grid-template-columns:1fr}.shot-filter-item--keyword{grid-column:auto}}
.shot-loading.el-card{display:block;padding:0}
.shot-loading:deep(.el-card__body){width:100%;box-sizing:border-box;padding:30px}
.shot-empty.el-empty{padding:30px;background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg)}
.shot-empty p{max-width:600px;margin:0;color:var(--sg-text-muted);font-size:12px;text-align:center}
.project-context__tags {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

@media (max-width: 1180px) {
  .project-context__tags { justify-content: flex-start; }
}

.shot-page.shot-page--table { padding-bottom: 16px; }
.shot-page.shot-page--schedule { padding-bottom: 12px; }


.shot-drag-handle {
  color: var(--sg-text-muted);
  cursor: grab;
  font-size: 16px;
}

.shot-drag-handle:active { cursor: grabbing; }
.shot-drag-handle.is-disabled { color: var(--sg-border-strong); cursor: not-allowed; opacity: .55; }

.shot-data-table:deep(.shot-row--results td.el-table__cell) {
  background: var(--sg-accent-soft);
}
.shot-data-table:deep(.shot-row--ghost td.el-table__cell) {
  background: var(--sg-accent-soft);
}

.shot-data-table:deep(.shot-row--chosen td.el-table__cell) {
  box-shadow: inset 0 1px 0 rgba(255,182,87,.35), inset 0 -1px 0 rgba(255,182,87,.35);
}
.shot-row-actions { flex-wrap: wrap; gap: 4px; white-space: normal; }
.shot-card :deep(.el-card__body) { display: flex; flex-direction: column; height: 100%; box-sizing: border-box; }
.shot-card__actions { margin-top: auto; padding-top: 12px; border-top: 1px solid var(--sg-border); }
.shot-card footer { margin-bottom: 12px; }
.task-date-cell { white-space: nowrap; font-variant-numeric: tabular-nums; }

/* 批量分配：操作、核对表格与汇总分别成区，减少行内无效留白。 */
.shot-batch-assign-drawer :deep(.el-drawer__header) { padding-bottom: 16px; border-bottom: 1px solid var(--sg-border); margin-bottom: 16px; }
.shot-batch-assign-drawer :deep(.el-drawer__footer) { padding-top: 16px; border-top: 1px solid var(--sg-border); }
:global(.shot-batch-assign-drawer .el-drawer__body) { display: flex; flex-direction: column; }
:global(.shot-batch-assign-drawer .el-drawer__body > .el-alert) { flex-shrink: 0; }
.batch-assign-form { display: flex; flex-direction: column; flex: 1; min-height: 360px; }
.batch-assign-form > * { flex-shrink: 0; }
.batch-assign-form > .batch-assign-table { flex: 1 1 0; min-height: 180px; }
.batch-assign-form .batch-assign-summary { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; padding: 0; margin: 0 0 16px; background: transparent; }
.batch-assign-summary strong { font-size: 14px; }
.batch-assign-summary span { color: var(--sg-text-muted); }
.batch-assign-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 16px; margin-bottom: 20px; background: var(--sg-surface-soft); border: 1px solid var(--sg-border); border-radius: 10px; }
.batch-assign-toolbar__label { display: flex; flex-direction: column; gap: 4px; min-width: 112px; margin-right: auto; }
.batch-assign-toolbar__label strong { font-size: 13px; color: var(--sg-text); }
.batch-assign-toolbar__label span { font-size: 12px; color: var(--sg-text-muted); }
.batch-assign-toolbar :deep(.el-form-item) { flex: 0 1 300px; min-width: 180px; }
.batch-assign-toolbar :deep(.el-button) { margin-left: 0; }
.batch-assign-table-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; margin-bottom: 10px; font-size: 12px; }
.batch-assign-table-heading strong { font-size: 13px; color: var(--sg-text); }
.batch-assign-table-heading span { color: var(--sg-text-muted); }
.batch-assign-table { border: 1px solid var(--sg-border); border-radius: 8px; }
.batch-assign-form :deep(.batch-assign-table .el-table__cell) { padding-top: 10px; padding-bottom: 10px; }
.batch-assign-form :deep(.batch-assign-table .el-form-item) { margin: 0; }
.batch-assign-form :deep(.batch-assign-table .el-form-item__error) { position: static; line-height: 1.4; }
.batch-assign-current { display: block; margin-top: 5px; color: var(--sg-text-muted); font-size: 11px; }
.batch-assign-counts { display: flex; align-items: flex-start; gap: 16px; margin: 16px 0 4px; padding: 14px 16px; background: var(--sg-surface-soft); border: 1px solid var(--sg-border); border-radius: 8px; font-size: 12px; }
.batch-assign-counts > strong { flex: 0 0 auto; padding-top: 4px; color: var(--sg-text-secondary); font-weight: 500; }
.batch-assign-counts__tags { display: flex; flex-wrap: wrap; gap: 8px; }
.batch-assign-counts :deep(.el-tag) { height: 28px; padding: 0 10px; }
@media (max-width: 640px) {
  .batch-assign-toolbar__label { flex-basis: 100%; }
  .batch-assign-toolbar :deep(.el-form-item) { flex: 1 1 180px; }
  .batch-assign-counts { flex-direction: column; gap: 8px; }
}
.batch-assign-form,
.batch-assign-form :deep(.el-table),
.batch-assign-form :deep(.el-select__wrapper),
.batch-assign-form :deep(.el-select__input),
.batch-assign-form .batch-assign-current { font-size: 12px; }
:global(.batch-assign-member-options .el-select-dropdown__item) { font-size: 12px; }

.storyboard { display: block; columns: auto; --story-card-width: 280px; }
.storyboard--small { --story-card-width: 220px; }.storyboard--large { --story-card-width: 360px; }
.storyboard__tools { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.storyboard__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, var(--story-card-width)), 1fr)); gap: 12px; }
.storyboard .story-frame { display: block; width: auto; margin: 0; padding: 0; cursor: default; }
.story-frame.is-active { border-color: var(--sg-accent); }
.story-frame__description { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 36px; line-height: 18px; }
.story-frame__summary { display: flex; justify-content: space-between; gap: 10px; color: var(--sg-text-muted); font-size: 12px; }
.story-frame__heading h3 { flex: 1; min-width: 0; }.story-frame__heading h3 .el-button { white-space: normal; text-align: left; }
.storyboard .story-frame { min-width: 0; border-radius: 10px; overflow: hidden; }
.storyboard .story-frame :deep(.el-card__body) { display: flex; flex-direction: column; padding: 0; height: 100%; }
.story-frame__media { position: relative; width: 100%; aspect-ratio: 16/9; background: var(--sg-media-stage-bg); }
.story-frame__media .shot-thumb { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 0; }
.story-frame__content { display: grid; gap: 8px; min-width: 0; padding: 12px; }
.story-frame__heading { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.story-frame__heading h3 { margin: 0; font-size: 13px; line-height: 1.5; overflow-wrap: anywhere; }
.story-frame__description { font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
.story-frame__actions { padding-top: 8px; border-top: 1px solid var(--sg-border); }
</style>

<style scoped src="../../assets/styles/filter-toolbar.css"></style>

<style>
.shot-results-drawer .el-drawer__header { margin-bottom: 8px; padding: 14px; }
.shot-results-drawer .el-drawer__body { padding: 0 12px 12px; }
</style>
