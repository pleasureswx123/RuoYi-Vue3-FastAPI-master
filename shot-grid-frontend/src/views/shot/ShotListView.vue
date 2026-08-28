<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Grid, List, Plus, Refresh, RefreshLeft, Search, Switch, Upload, User, VideoCamera, VideoPlay, View } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'

import { getProjectDetail, getProjectPage } from '@/api/shot-grid/projects'
import { useTaskStartDialog } from '@/views/task/useTaskStartDialog'
import TaskStartDialog from '@/views/task/components/TaskStartDialog.vue'
import { batchAssignShotTasks, batchDeleteShots, getEpisodePage, getScenePage, getShotDetail, getShotPage, listShotAssignees, reorderShot } from '@/api/shot-grid/shots'
import { assertPositiveId } from '@/api/shot-grid/projects'
import { useTaskStatePolling } from '@/composables/useTaskStatePolling'
import { useCurrentTime } from '@/composables/useCurrentTime'
import { formatTaskDateTime, taskTimeReminder } from '@/views/task/taskPresentation'
import { useSessionStore } from '@/store/modules/session'
import { tagTypeFromTone } from '@/utils/tag'
import TableActionButton from '@/components/TableActionButton.vue'
import { projectRoleMeta, storageMeta } from '@/views/project/projectPresentation'
import ProjectStatePanel from '@/views/project/components/ProjectStatePanel.vue'
import ProtectedThumbnail from '@/views/shot/components/ProtectedThumbnail.vue'
import EpisodeSceneCreateDialog from '@/views/shot/components/EpisodeSceneCreateDialog.vue'
import ShotDetailView from '@/views/shot/ShotDetailView.vue'
import ShotFormDialog from '@/views/shot/components/ShotFormDialog.vue'
import ShotAssignDialog from '@/views/shot/components/ShotAssignDialog.vue'
import ShotImportDialog from '@/views/shot/components/ShotImportDialog.vue'
import { directoryStatusMeta, formatShotDuration, shotAssigneeName, shotAssigneeOptionLabel, shotErrorState, shotStatusMeta, shotStatusTagClass } from '@/views/shot/shotPresentation'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const projects = ref([])
const project = ref(null)
const episodes = ref([])
const scenes = ref([])
const members = ref([])
const shots = ref([])
const selectedShotIds = ref(new Set())
const total = ref(0)
const hasNext = ref(false)
const projectsLoading = ref(false)
const shotsLoading = ref(false)
const scenesLoading = ref(false)
const projectsError = ref(null)
const shotsError = ref(null)
const viewMode = ref('table')
const showDetail = ref(false)
const detailShotId = ref(null)
const showCreate = ref(false)
const showImport = ref(false)
const showEdit = ref(false)
const editingShot = ref(null)
const editContext = ref(null)
const deleting = ref(false)
const assigning = ref(false)
const startingOperation = ref(null)
const currentTime = useCurrentTime()
const { startDialog, requestStartDialog, closeStartDialog, finishStartDialog, failStartDialog } = useTaskStartDialog()
const reordering = ref(false)
const sceneOrderFullyLoaded = ref(false)
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
const shotTableRef = ref(null)
const projectContext = reactive({ projectId: '', scope: '' })
const batchAssignForm = reactive({ assigneeUserId: '' })
const query = reactive({
  keyword: '', episodeId: '', sceneId: '', shotStatus: '', assigneeUserId: '',
  pageNum: 1, pageSize: 100, orderByColumn: 'sortOrder', isAsc: 'ascending'
})
const appliedQuery = ref('')
let projectController = null
let shotController = null
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
const canViewAll = computed(() => hasPermission('shotgrid:project:all'))
const isDirector = computed(() => project.value?.myProjectRole === 'director' || wildcard.value || canViewAll.value)
const projectAllowsWrites = computed(() => project.value && !['completed', 'archived'].includes(project.value.projectStatus) && project.value.storageStatus === 'ready')
const canCreate = computed(() => isDirector.value && hasPermission('shotgrid:shot:add') && projectAllowsWrites.value)
const canImport = computed(() => isDirector.value && hasPermission('shotgrid:shot:import') && projectAllowsWrites.value)
const canEdit = computed(() => isDirector.value && hasPermission('shotgrid:shot:edit') && projectAllowsWrites.value)
const canDelete = computed(() => isDirector.value && hasPermission('shotgrid:shot:archive') && projectAllowsWrites.value)
const canAssign = computed(() => isDirector.value && hasPermission('shotgrid:task:assign') && projectAllowsWrites.value)
const canStart = computed(() => isDirector.value && hasPermission('shotgrid:task:start') && projectAllowsWrites.value)
const startDisabled = computed(() => shotsLoading.value || Boolean(startingOperation.value) || assigning.value || deleting.value || reordering.value)
const canCreateEpisode = computed(() => isDirector.value && hasPermission('shotgrid:episode:add') && projectAllowsWrites.value)
const canCreateScene = computed(() => isDirector.value && hasPermission('shotgrid:scene:add') && projectAllowsWrites.value)
const isSceneOrderScope = computed(() => (
  viewMode.value === 'table' &&
  Boolean(query.episodeId) &&
  Boolean(query.sceneId) &&
  !query.keyword.trim() &&
  !query.shotStatus &&
  !query.assigneeUserId &&
  query.orderByColumn === 'sortOrder' &&
  query.isAsc === 'ascending'
))
const sceneSequenceConsistent = computed(() => (
  shots.value.every((shot, index) => {
    const expected = index + 1
    return (
      Number(shot?.sequencePosition) === expected &&
      Number(shot?.shotNo) === expected &&
      shot?.shotCode === `S${String(expected).padStart(3, '0')}`
    )
  })
))
const canDragSort = computed(() => (
  canEdit.value &&
  !shotsLoading.value &&
  !reordering.value &&
  isSceneOrderScope.value &&
  sceneOrderFullyLoaded.value &&
  sceneSequenceConsistent.value &&
  shots.value.length > 1
))
const dragSortHint = computed(() => {
  if (!canEdit.value || viewMode.value !== 'table' || shotsLoading.value) return ''
  if (!query.episodeId) return ' · 选择具体集和场次后可排序'
  if (!query.sceneId) return ' · 请选择具体场次后可排序'
  if (query.keyword.trim() || query.shotStatus || query.assigneeUserId) return ' · 清空附加筛选后可排序'
  if (total.value > MAX_SCENE_SORT_SHOTS) return ` · 当前场次超过 ${MAX_SCENE_SORT_SHOTS} 镜，不能在线拖拽排序`
  if (!sceneOrderFullyLoaded.value) return ' · 正在加载完整场次，完成后可排序'
  if (!sceneSequenceConsistent.value) return ' · 当前场次镜头号不连续，请先完成历史数据治理后再排序'
  if (shots.value.length <= 1) return ' · 当前场次无需排序'
  if (!shots.value.some(isShotOrderMutable)) return ' · 当前场次镜头均已冻结，不能调整顺序'
  return ' · 拖动左侧手柄调整顺序，Sxxx 会同步更新；已开始制作或目录已冻结的镜头不可调整'
})
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / query.pageSize)))
const currentProjectId = computed(() => {
  try { return assertPositiveId(projectContext.projectId, '项目') } catch { return null }
})
const creatorMembers = computed(() => members.value.filter(member => member.projectRole === 'creator'))
const selectedShots = computed(() => shots.value.filter(shot => selectedShotIds.value.has(Number(shot.shotId))))
const hasAssignedSelection = computed(() => selectedShots.value.some(shot => Boolean(shot.assignee)))
const batchAssignLabel = computed(() => hasAssignedSelection.value ? '批量重新分配' : '批量分配')
const detailShot = computed(() => shots.value.find(shot => Number(shot.shotId) === detailShotId.value) || null)
const detailDrawerTitle = computed(() => detailShot.value ? `镜头详情 · ${detailShot.value.shotCode}` : '镜头详情')
const canDeleteSelection = computed(() => Boolean(selectedShots.value.length) && selectedShots.value.every(shot => canDeleteShot(shot)))
const { pollingError } = useTaskStatePolling({
  getDelay: () => {
    if (!projectAllowsWrites.value || shotsLoading.value || scenesLoading.value || shotsError.value ||
        showDetail.value || showCreate.value || showImport.value || showEdit.value || editingShotId.value ||
        showHierarchyCreate.value || showBatchAssign.value || startingOperation.value || singleAssignContext.value || assigningShotId.value ||
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
const shotFilterRules = {
  keyword: [{ max: 200, message: '搜索内容不能超过 200 个字符', trigger: 'blur' }],
  episodeId: [optionalPositiveIdRule('请选择有效集')],
  sceneId: [optionalPositiveIdRule('请选择有效场次')],
  shotStatus: [{
    validator: (_rule, value, callback) => {
      if (value && !['unassigned', 'not_started', 'preparing', 'in_progress', 'reviewing', 'revision', 'completed'].includes(value)) {
        callback(new Error('请选择有效镜头状态'))
        return
      }
      callback()
    },
    trigger: 'change'
  }],
  assigneeUserId: [optionalPositiveIdRule('请选择有效制作人')]
}
const batchAssignRules = {
  assigneeUserId: [{
    validator: (_rule, value, callback) => {
      const userId = Number(value)
      const memberExists = creatorMembers.value.some(item => Number(item.userId) === userId)
      if (!Number.isSafeInteger(userId) || userId <= 0 || !memberExists) {
        callback(new Error('请选择要分配的新制作人'))
        return
      }
      callback()
    },
    trigger: 'change'
  }]
}

function shotTimeState(shot) {
  return taskTimeReminder({ taskStatus: shot.status, expectedEndTime: shot.expectedEndTime }, currentTime.value)
}

function canStartShot(shot) {
  return Boolean(
    canStart.value && hasPermission('shotgrid:shot:query') && shot?.status === 'not_started' &&
    shot.allowedActions?.includes('task.start') &&
    Number.isSafeInteger(shot.taskId) && shot.taskId > 0 &&
    Number.isSafeInteger(shot.taskLockVersion) && shot.taskLockVersion >= 0 &&
    Number.isSafeInteger(shot.lockVersion) && shot.lockVersion >= 0
  )
}

function isCurrentStart(operation) {
  return !disposed && startingOperation.value === operation &&
    currentProjectId.value === operation.projectId && projectGeneration === operation.projectGeneration
}

async function confirmStartShot(shot) {
  if (!canStartShot(shot) || startDisabled.value) return
  const operation = Object.freeze({
    projectId: currentProjectId.value, projectGeneration,
    shotId: shot.shotId, taskId: shot.taskId,
    lockVersion: shot.taskLockVersion, shotLockVersion: shot.lockVersion
  })
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
      name: [detail.episodeCode, detail.sceneCode, detail.shotCode].join(' / '),
      assigneeName: shotAssigneeName(detail.task.assignee || shot.assignee, members.value),
      shot: detail, task: detail.task, taskId: operation.taskId,
      command: { lockVersion: operation.lockVersion, shotLockVersion: operation.shotLockVersion, assetsConfirmed: true },
      validateContext: () => {
        const currentShot = shots.value.find(item => item.shotId === operation.shotId)
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
  } catch (error) {
    if (error === 'cancel' || error === 'close' || !isCurrentStart(operation)) return
    ElMessage.error(error?.message || '确认开工失败，请刷新后重试')
    if (Number(error?.httpStatus || error?.status) === 409) await loadShots()
  } finally {
    if (startingOperation.value === operation) startingOperation.value = null
  }
}

function canDeleteShot(shot) {
  return canDelete.value && ['unassigned', 'not_started'].includes(shot?.status)
}

function canEditShot(shot) {
  return canEdit.value && ['unassigned', 'not_started'].includes(shot?.status)
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
      ElMessage.warning('镜头状态或权限已变化，当前不能分配任务。')
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

function canSelectShot(shot) {
  return canAssignShot(shot) || canDeleteShot(shot)
}

function isShotSelectable(shot) {
  return !deleting.value && !assigning.value && canSelectShot(shot)
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
    projects.value = await fetchAllPages(
      (params, options) => getProjectPage(params, options),
      { scope: projectContext.scope || undefined, orderByColumn: 'projectName', isAsc: 'ascending' },
      controller.signal
    )
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
  closeStartDialog()
  startingOperation.value = null
  const projectId = currentProjectId.value
  closeDetailDrawer()
  shotController?.abort()
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
        { lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' },
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
      { lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' },
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
  if (!projectId) return
  if (!existingController) shotController?.abort()
  const controller = existingController || new AbortController()
  shotController = controller
  if (!background) {
    clearShotSelection()
    shotsLoading.value = true
    shotsError.value = null
    sceneOrderFullyLoaded.value = false
    appliedQuery.value = JSON.stringify(query)
  }
  const fullScene = isSceneOrderScope.value
  try {
    const params = {
      keyword: query.keyword.trim() || undefined,
      episodeId: query.episodeId || undefined,
      sceneId: query.sceneId || undefined,
      shotStatus: query.shotStatus || undefined,
      assigneeUserId: query.assigneeUserId || undefined,
      pageNum: query.pageNum,
      pageSize: query.pageSize,
      orderByColumn: query.orderByColumn,
      isAsc: query.isAsc
    }
    const response = await getShotPage(projectId, params, { signal: controller.signal })
    if (disposed || controller.signal.aborted || shotController !== controller) return
    let loadedRows = Array.isArray(response.rows) ? response.rows : []
    const loadedTotal = Number(response.total || 0)
    if (fullScene && loadedTotal <= MAX_SCENE_SORT_SHOTS && loadedRows.length < loadedTotal) {
      loadedRows = await fetchAllPages(
        (pageParams, options) => getShotPage(projectId, pageParams, options),
        { ...params, pageNum: undefined, pageSize: undefined },
        controller.signal
      )
    }
    if (disposed || controller.signal.aborted || shotController !== controller) return
    shots.value = loadedRows
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
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && !controller.signal.aborted && shotController === controller && !disposed) {
      if (background) throw error
      shots.value = []
      total.value = 0
      shotsError.value = shotErrorState(error, '镜头列表加载失败')
    }
  } finally {
    if (!background && shotController === controller) shotsLoading.value = false
  }
}

async function submitFilters() {
  const valid = shotFilterForm.value
    ? await shotFilterForm.value.validate().catch(() => false)
    : false
  if (!valid) return
  query.pageNum = 1
  await loadShots()
}

function changeEpisodeFilter() {
  query.sceneId = ''
  loadScenes(false)
  submitFilters()
}

function resetFilters() {
  shotFilterForm.value?.resetFields()
  shotFilterForm.value?.clearValidate()
  query.pageNum = 1
  loadScenes(false)
  loadShots()
}

function changePage(page) {
  if (page < 1 || page > pageCount.value || page === query.pageNum) return
  query.pageNum = page
  loadShots()
}

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
    ['unassigned', 'not_started'].includes(shot?.status) &&
    !shot?.storageDirName &&
    shot?.directoryStatus === 'not_created' &&
    !shot?.latestVersion
  )
}

function shotOrderLockReason(shot) {
  if (!['unassigned', 'not_started'].includes(shot?.status)) return '该镜头已开始制作，不能调整顺序'
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
      ElMessage.success(`顺序已受理，正在迁移存量目录；完成后自动更新为 S${String(sequencePosition).padStart(3, '0')}`)
      await loadProjectContext()
    } else {
      ElMessage.success(`已调整为本场第 ${sequencePosition} 镜（${result?.shotCode || `S${String(sequencePosition).padStart(3, '0')}`}）`)
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
  if (assigning.value || !selectedShots.value.length) return
  const valid = batchAssignFormRef.value
    ? await batchAssignFormRef.value.validate().catch(() => false)
    : false
  if (!valid) return
  const assigneeUserId = Number(batchAssignForm.assigneeUserId)
  const member = creatorMembers.value.find(item => Number(item.userId) === assigneeUserId)
  if (!member) {
    ElMessage.warning('请先选择要分配的新制作人')
    return
  }
  const blocked = selectedShots.value.find(shot => !canAssignShot(shot))
  if (blocked) {
    ElMessage.warning(`${blocked.shotCode} 当前不能分配或改派，请刷新状态；仅未开工任务可改派`)
    return
  }
  const targetProjectId = currentProjectId.value
  const items = selectedShots.value.map(shot => ({
    shotId: shot.shotId,
    taskLockVersion: shot.taskLockVersion
  }))
  if (currentProjectId.value !== targetProjectId) return
  assigning.value = true
  try {
    await batchAssignShotTasks(targetProjectId, assigneeUserId, items)
    ElMessage.success(`已将 ${items.length} 个镜头分配给 ${shotAssigneeName(member)}`)
    if (currentProjectId.value === targetProjectId) {
      showBatchAssign.value = false
      resetBatchAssignForm()
      clearShotSelection()
      await loadShots()
    }
  } catch (error) {
    const state = shotErrorState(error, '镜头批量分配失败')
    ElMessage.error(`${state.title}：${state.message}`)
    if (state.status === 409 && currentProjectId.value === targetProjectId) await loadShots()
  } finally { assigning.value = false }
}

function openBatchAssignDialog() {
  if (!selectedShots.value.length || assigning.value || deleting.value) return
  resetBatchAssignForm()
  showBatchAssign.value = true
}

function closeBatchAssignDialog(force = false) {
  if (assigning.value && !force) return
  showBatchAssign.value = false
  resetBatchAssignForm()
}

function resetBatchAssignForm() {
  batchAssignFormRef.value?.resetFields()
  batchAssignFormRef.value?.clearValidate()
  batchAssignForm.assigneeUserId = ''
}

async function openEditDialog(shot) {
  if (!canEditShot(shot) || deleting.value || editingShotId.value) return
  const targetProjectId = currentProjectId.value
  const targetShotId = Number(shot.shotId)
  const generation = ++operationGeneration
  editingShotId.value = targetShotId
  try {
    const response = await getShotDetail(targetProjectId, targetShotId)
    if (currentProjectId.value !== targetProjectId || generation !== operationGeneration) return
    editingShot.value = response.data
    editContext.value = Object.freeze({ projectId: targetProjectId, shotId: targetShotId, operationGeneration: generation })
    showEdit.value = true
  } catch (error) {
    const state = shotErrorState(error, '镜头信息加载失败')
    ElMessage.error(`${state.title}：${state.message}`)
  } finally {
    if (editingShotId.value === targetShotId) editingShotId.value = null
  }
}

function closeEditDialog() {
  showEdit.value = false
  editingShot.value = null
  editContext.value = null
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
      { lifecycleStatus: 'active', orderByColumn: 'sortOrder', isAsc: 'ascending' },
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
    closeCreateDialog()
    closeImportDialog()
    closeEditDialog()
    closeSingleAssign()
    closeDetailDrawer()
    closeBatchAssignDialog(true)
    operationGeneration += 1
    query.pageNum = 1
    query.episodeId = ''
    query.sceneId = ''
    query.assigneeUserId = ''
    resetBatchAssignForm()
    loadProjectContext()
  }
})
watch(() => appliedQuery.value, closeSingleAssign)
watch(() => projectContext.scope, () => loadProjects())
watch(viewMode, () => {
  query.pageNum = 1
  loadShots()
})
watch(
  [canDragSort, sceneOrderFullyLoaded, () => shots.value.map(shot => shot.shotId).join(','), () => query.pageNum],
  () => nextTick(initRowSortable),
  { flush: 'post' }
)
onMounted(() => loadProjects(route.query.projectId))
onBeforeUnmount(() => { disposed = true; closeSingleAssign(); destroyRowSortable(); projectController?.abort(); shotController?.abort(); sceneController?.abort(); episodeRefreshController?.abort() })
</script>

<template>
  <TaskStartDialog v-if="startDialog" :context="startDialog" @close="closeStartDialog" @started="finishStartDialog" @failed="failStartDialog" />
  <section class="sg-page shot-page">
    <header class="sg-page-heading shot-heading">
      <div><p class="sg-eyebrow">SHOTS</p><h2 class="sg-page-title">镜头管理</h2><p class="sg-page-description">按项目查看和维护镜头，可在表格、卡片与故事板之间灵活切换。</p></div>
      <div class="shot-heading__actions"><el-button v-if="canCreateEpisode" @click="openHierarchyCreate('episode')">新建集</el-button><el-button v-if="canCreateScene" :disabled="!episodes.length" @click="openHierarchyCreate('scene')">新建场次</el-button><el-button v-if="canImport" :icon="Upload" @click="openImportDialog">导入 Excel</el-button><el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreateDialog">新建镜头</el-button></div>
    </header>

    <ProjectStatePanel v-if="projectsError" :title="projectsError.title" :message="projectsError.message" :retryable="projectsError.retryable" @retry="loadProjects" />
    <template v-else>
      <el-form ref="projectContextForm" :model="projectContext" :rules="projectContextRules" class="project-context" size="large" inline label-position="top" aria-label="项目选择">
        <el-form-item label="当前项目" prop="projectId"><el-select v-model="projectContext.projectId" class="sg-select" :placeholder="projectsLoading ? '正在加载项目…' : '请选择项目'" :disabled="projectsLoading"><el-option :label="projectsLoading ? '正在加载项目…' : '请选择项目'" value="" /><el-option v-for="item in projects" :key="item.projectId" :label="`${item.projectCode} · ${item.projectName}`" :value="String(item.projectId)" /></el-select></el-form-item>
        <el-form-item v-if="canViewAll" label="项目范围" prop="scope"><el-select v-model="projectContext.scope" class="sg-select" placeholder="我的项目"><el-option label="我的项目" value="" /><el-option label="全部项目" value="all" /></el-select></el-form-item>
        <div v-if="project" class="project-context__tags"><el-tag size="small" effect="plain" round type="primary">{{ project.projectTypeName }}</el-tag><el-tag size="small" effect="plain" round type="info">{{ project.aspectRatio }}</el-tag><el-tag size="small" effect="plain" round :type="projectRoleMeta(project.myProjectRole).type">我的角色：{{ projectRoleMeta(project.myProjectRole).label }}</el-tag><el-tag size="small" effect="plain" round :type="tagTypeFromTone(storageMeta(project.storageStatus).tone)">{{ storageMeta(project.storageStatus).label }}</el-tag></div>
      </el-form>

      <el-empty v-if="!projectContext.projectId && !projectsLoading" class="shot-empty" description="当前范围暂无可选项目"><p>请先创建项目，或请项目管理人将你加入项目；如可查看全部项目，也可切换“全部项目”。</p></el-empty>

      <template v-else-if="projectContext.projectId">
        <el-form ref="shotFilterForm" :model="query" :rules="shotFilterRules" class="shot-filters" size="large" aria-label="镜头筛选">
          <el-form-item class="shot-filter-item shot-filter-item--keyword" prop="keyword">
            <el-input v-model="query.keyword" class="shot-search" :prefix-icon="Search" maxlength="200" clearable placeholder="Sxxx、制作内容、台词或场次名称" aria-label="搜索镜头" />
          </el-form-item>
          <el-form-item class="shot-filter-item" prop="episodeId">
            <el-select v-model="query.episodeId" class="sg-select" placeholder="全部集" aria-label="按集筛选" @change="changeEpisodeFilter"><el-option label="全部集" value="" /><el-option v-for="episode in episodes" :key="episode.episodeId" :label="`${episode.episodeCode} ${episode.episodeName || ''}`" :value="String(episode.episodeId)" /></el-select>
          </el-form-item>
          <el-form-item class="shot-filter-item" prop="sceneId">
            <el-select v-model="query.sceneId" class="sg-select" :placeholder="scenesLoading ? '加载场次中…' : '全部场次'" aria-label="按场次筛选" :disabled="!query.episodeId || scenesLoading" @change="submitFilters"><el-option :label="scenesLoading ? '加载场次中…' : '全部场次'" value="" /><el-option v-for="scene in scenes" :key="scene.sceneId" :label="`${scene.sceneCode} ${scene.sceneName || ''}`" :value="String(scene.sceneId)" /></el-select>
          </el-form-item>
          <el-form-item class="shot-filter-item" prop="shotStatus">
            <el-select v-model="query.shotStatus" class="sg-select" placeholder="全部状态" aria-label="按状态筛选" @change="submitFilters"><el-option label="全部状态" value="" /><el-option v-for="status in ['unassigned','not_started','preparing','in_progress','reviewing','revision','completed']" :key="status" :label="shotStatusMeta(status).label" :value="status" /></el-select>
          </el-form-item>
          <el-form-item class="shot-filter-item" prop="assigneeUserId">
            <el-select v-model="query.assigneeUserId" class="sg-select" placeholder="全部制作人" aria-label="按制作人筛选" @change="submitFilters"><el-option label="全部制作人" value="" /><el-option v-for="member in creatorMembers" :key="member.userId" :label="shotAssigneeOptionLabel(member)" :value="String(member.userId)" /></el-select>
          </el-form-item>
          <el-form-item class="shot-filter-actions">
            <el-button type="primary" :icon="Search" :loading="shotsLoading" @click="submitFilters">查询</el-button>
            <el-button :icon="RefreshLeft" :disabled="shotsLoading" @click="resetFilters">重置</el-button>
            <el-button :icon="Refresh" circle aria-label="刷新镜头" :disabled="shotsLoading" @click="loadShots()" />
          </el-form-item>
        </el-form>

        <div class="shot-list-toolbar"><div class="shot-list-toolbar__summary"><strong>{{ total }}</strong><span>个镜头<span v-if="shotsLoading"> · 正在刷新</span><span v-else>{{ dragSortHint }}</span></span><template v-if="viewMode === 'table' && selectedShots.length"><el-button v-if="canAssign" text type="primary" :loading="assigning" :disabled="deleting" @click="openBatchAssignDialog">{{ batchAssignLabel }}（{{ selectedShots.length }}）</el-button><el-button v-if="canDelete" text type="danger" :icon="Delete" :disabled="!canDeleteSelection || deleting || assigning" :loading="deleting" :title="!canDeleteSelection ? '选中项包含已开始任务，不能批量删除' : ''" @click="confirmDeleteShots(selectedShots)">批量删除（{{ selectedShots.length }}）</el-button></template></div><el-radio-group v-model="viewMode" class="shot-list-toolbar__views" size="small" aria-label="镜头视图"><el-radio-button value="table"><el-icon><List /></el-icon>表格</el-radio-button><el-radio-button value="card"><el-icon><Grid /></el-icon>卡片</el-radio-button><el-radio-button value="storyboard"><el-icon><VideoCamera /></el-icon>故事板</el-radio-button></el-radio-group></div>

        <el-alert v-if="pollingError" :title="pollingError" type="warning" show-icon :closable="false" />
        <ProjectStatePanel v-if="shotsError" :title="shotsError.title" :message="shotsError.message" :retryable="shotsError.retryable" @retry="loadProjectContext" />
        <el-card v-else-if="viewMode !== 'table' && shotsLoading && !shots.length" class="shot-loading" shadow="never" aria-busy="true"><el-skeleton animated :rows="8" /></el-card>
        <el-empty v-else-if="viewMode !== 'table' && !shots.length" class="shot-empty" description="当前筛选没有镜头"><p>可以调整集、场次、状态或制作人筛选；项目管理人也可以新建或导入镜头。</p></el-empty>

        <div v-else-if="viewMode === 'table'" class="shot-table-wrap">
          <el-table ref="shotTableRef" v-loading="shotsLoading" class="shot-data-table" :data="shots" row-key="shotId" max-height="620" empty-text="当前筛选没有镜头" @selection-change="handleShotSelectionChange">
            <template #empty><el-empty class="shot-empty" description="当前筛选没有镜头"><p>可以调整集、场次、状态或制作人筛选；项目管理人也可以新建或导入镜头。</p></el-empty></template>
            <!-- <el-table-column v-if="canDragSort" width="38" fixed="left" align="center"><template #default="scope"><el-icon class="shot-drag-handle" :class="{ 'is-disabled': !isShotOrderMutable(scope.row) }" :title="isShotOrderMutable(scope.row) ? '拖拽调整场内顺序，Sxxx 将同步更新' : shotOrderLockReason(scope.row)"><Rank /></el-icon></template></el-table-column> -->
            <el-table-column type="selection" width="48" fixed="left" align="center" :selectable="isShotSelectable" reserve-selection />
            <el-table-column label="集 / 场 / 镜头" width="180" fixed="left">
              <template #default="scope"><div v-if="scope?.row" class="shot-identity"><strong>{{ scope.row.episodeCode }} / {{ scope.row.sceneCode }} / {{ scope.row.shotCode }}</strong><small>本场第 {{ scope.row.shotNo }} 镜 · {{ formatShotDuration(scope.row.durationMs) }}</small></div></template>
            </el-table-column>
            <el-table-column label="缩略图" width="115">
              <template #default="scope"><ProtectedThumbnail v-if="scope?.row" class="shot-thumb shot-thumb--small" :thumbnail="scope.row.thumbnail" :video="scope.row.proxyMedia" :alt="`${scope.row.shotCode} 缩略图`" /></template>
            </el-table-column>
            <el-table-column label="制作内容" width="280">
              <template #default="scope"><div v-if="scope?.row" class="shot-description">{{ scope.row.description }}</div></template>
            </el-table-column>
            <el-table-column prop="expectedStartTime" label="开始时间" width="150" class-name="task-expected-start">
              <template #default="{ row }"><span class="task-date-cell">{{ formatTaskDateTime(row.expectedStartTime) }}</span></template>
            </el-table-column>
            <el-table-column prop="expectedEndTime" label="结束时间" width="150" class-name="task-expected-end">
              <template #default="{ row }"><span class="task-date-cell">{{ formatTaskDateTime(row.expectedEndTime) }}</span></template>
            </el-table-column>
            <el-table-column label="镜头参数" width="190">
              <template #default="scope"><div v-if="scope?.row" class="shot-parameters"><span>{{ scope.row.shotSize || '—' }}</span><small>{{ [scope.row.cameraPosition, scope.row.cameraMovement, scope.row.focalLength].filter(Boolean).join(' · ') || '暂无参数' }}</small></div></template>
            </el-table-column>
            <el-table-column label="场景 / 角色" width="160">
              <template #default="scope"><div v-if="scope?.row" class="shot-assets"><el-tag v-for="asset in scope.row.environmentAssets" :key="`environment-${asset.assetId}`" :type="tagTypeFromTone('environment')" size="small" effect="plain" round>场景 · {{ asset.assetName }}</el-tag><el-tag v-for="asset in scope.row.characterAssets" :key="`character-${asset.assetId}`" :type="tagTypeFromTone('character')" size="small" effect="plain" round>角色 · {{ asset.assetName }}</el-tag><span v-if="!scope.row.environmentAssets.length && !scope.row.characterAssets.length" class="shot-assets__empty">—</span></div></template>
            </el-table-column>
            <el-table-column label="台词 / 对白" width="150">
              <template #default="scope"><div v-if="scope?.row" class="shot-long-text">{{ scope.row.dialogue || '—' }}</div></template>
            </el-table-column>
            <el-table-column label="音效" width="220">
              <template #default="scope"><div v-if="scope?.row" class="shot-long-text">{{ scope.row.soundEffect || '—' }}</div></template>
            </el-table-column>
            <el-table-column label="色调参考" width="220">
              <template #default="scope"><div v-if="scope?.row" class="shot-long-text">{{ scope.row.colorReference || '—' }}</div></template>
            </el-table-column>
            <el-table-column label="备注" width="220">
              <template #default="scope"><div v-if="scope?.row" class="shot-long-text">{{ scope.row.remark || '—' }}</div></template>
            </el-table-column>
            <!-- <el-table-column label="最新反馈" width="120">
              <template #default="scope"><div v-if="scope?.row" class="feedback-cell">{{ scope.row.latestFeedback?.content || '—' }}</div></template>
            </el-table-column> -->
            <el-table-column label="时间状态" fixed="right" width="120" class-name="task-time-state">
              <template #default="{ row }"><el-tag :type="tagTypeFromTone(shotTimeState(row).tone)" size="small" effect="light" round>{{ shotTimeState(row).label }}</el-tag></template>
            </el-table-column>
            <el-table-column label="制作人" fixed="right" width="110">
              <template #default="scope"><span v-if="scope?.row" class="sg-table-assignee" :class="{ 'is-unassigned': !scope.row.assignee }">{{ shotAssigneeName(scope.row.assignee, members) }}</span></template>
            </el-table-column>
            <el-table-column label="状态" fixed="right" width="125">
              <template #default="scope">
                <div v-if="scope?.row">
                  <el-tag class="shot-status-tag" :class="shotStatusTagClass(scope.row.status)"
                          :type="tagTypeFromTone(shotStatusMeta(scope.row.status).tone)" size="small" effect="light"
                          round>{{ shotStatusMeta(scope.row.status).label }}
                  </el-tag>
                  <el-tag v-if="scope.row.directoryStatus === 'failed'" class="shot-status-tag shot-status-tag--directory-failed"
                          :type="tagTypeFromTone(directoryStatusMeta(scope.row.directoryStatus).tone)" size="small"
                          effect="light" round>{{ directoryStatusMeta(scope.row.directoryStatus).label }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" width="420">
              <template #default="scope">
                <div v-if="scope?.row" class="shot-row-actions">
                  <TableActionButton v-if="canStartShot(scope.row)" label="开始任务" type="primary" :plain="false" :icon="VideoPlay" :loading="startingOperation?.shotId === scope.row.shotId" :disabled="startDisabled" @click="confirmStartShot(scope.row)" />
                  <TableActionButton v-if="canOpenShotAssign(scope.row)" :label="scope.row.task || scope.row.taskLockVersion != null ? '改派任务' : '分配任务'" type="info" :icon="scope.row.task || scope.row.taskLockVersion != null ? Switch : User" :loading="assigningShotId === Number(scope.row.shotId)" :disabled="shotsLoading || assigning || deleting || Boolean(startingOperation) || Boolean(singleAssignContext) || Boolean(assigningShotId)" @click="openSingleAssign(scope.row)" />
                  <TableActionButton label="详情" :icon="View" @click="openShot(scope.row)" />
                  <TableActionButton v-if="canEditShot(scope.row)" label="编辑" :icon="Edit" :loading="editingShotId === Number(scope.row.shotId)" :disabled="deleting" @click="openEditDialog(scope.row)" />
                  <TableActionButton v-if="canDelete" label="删除" :hint="canDeleteShot(scope.row) ? '删除镜头' : '任务已经开始，不能删除'" type="danger" :icon="Delete" :disabled="!canDeleteShot(scope.row) || deleting" @click="confirmDeleteShots([scope.row])" />
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-else-if="viewMode === 'card'" class="shot-grid" :class="{ 'is-refreshing':shotsLoading }"><el-card v-for="shot in shots" :key="shot.shotId" class="shot-card" shadow="hover" role="link" tabindex="0" @click="openShot(shot)" @keydown.enter="openShot(shot)" @keydown.space.prevent="openShot(shot)"><div class="shot-card__media"><ProtectedThumbnail class="shot-thumb" :thumbnail="shot.thumbnail" :video="shot.proxyMedia" :alt="`${shot.shotCode} 缩略图`" /><span class="shot-card__duration">{{ formatShotDuration(shot.durationMs) }}</span></div><header><div><small>{{ shot.episodeCode }} / {{ shot.sceneCode }}</small><h3>{{ shot.shotCode }} · 第 {{ shot.shotNo }} 镜</h3></div><el-tag class="shot-status-tag" :class="shotStatusTagClass(shot.status)" :type="tagTypeFromTone(shotStatusMeta(shot.status).tone)" size="small" effect="light" round>{{ shotStatusMeta(shot.status).label }}</el-tag></header><p>{{ shot.description }}</p><footer><span>{{ shotAssigneeName(shot.assignee, members) }}</span><span>{{ shot.shotSize || '未设景别' }}</span><el-button v-if="canStartShot(shot)" size="small" type="primary" :icon="VideoPlay" :loading="startingOperation?.shotId === shot.shotId" :disabled="startDisabled" @click.stop="confirmStartShot(shot)" @keydown.stop>开始任务</el-button></footer></el-card></div>

        <div v-else class="storyboard" :class="{ 'is-refreshing':shotsLoading }"><el-card v-for="shot in shots" :key="shot.shotId" class="story-frame" shadow="hover" role="link" tabindex="0" @click="openShot(shot)" @keydown.enter="openShot(shot)" @keydown.space.prevent="openShot(shot)"><span class="story-frame__index" title="本场镜头序号">{{ String(shot.shotNo).padStart(2,'0') }}</span><ProtectedThumbnail class="shot-thumb" :thumbnail="shot.thumbnail" :video="shot.proxyMedia" :alt="`${shot.shotCode} 缩略图`" /><div><strong>{{ shot.episodeCode }} · {{ shot.sceneCode }} · {{ shot.shotCode }}</strong><p>{{ shot.description }}</p><small>本场第 {{ shot.shotNo }} 镜 · {{ formatShotDuration(shot.durationMs) }} · {{ shot.shotSize || '未设景别' }} · {{ shotAssigneeName(shot.assignee, members) }}</small><el-button v-if="canStartShot(shot)" size="small" type="primary" :icon="VideoPlay" :loading="startingOperation?.shotId === shot.shotId" :disabled="startDisabled" @click.stop="confirmStartShot(shot)" @keydown.stop>开始任务</el-button></div></el-card></div>

        <el-pagination v-if="shots.length && !sceneOrderFullyLoaded" class="shot-pagination" background layout="prev, pager, next, total" :current-page="query.pageNum" :page-size="query.pageSize" :total="total" :disabled="shotsLoading" aria-label="镜头分页" @current-change="changePage" />
      </template>
    </template>

    <ShotFormDialog v-if="showCreate && createProjectId && createOperationGeneration" :project-id="createProjectId" :operation-generation="createOperationGeneration" :episodes="episodes" :initial-episode-id="createInitialEpisodeId" :initial-scene-id="createInitialSceneId" @close="closeCreateDialog" @saved="handleSaved" @refresh="loadProjectContext" />
    <ShotFormDialog v-if="showEdit && editContext && editingShot" :project-id="editContext.projectId" :operation-generation="editContext.operationGeneration" :episodes="episodes" :shot="editingShot" @close="closeEditDialog" @saved="handleEdited" @refresh="handleEditRefresh" />
    <ShotAssignDialog v-if="singleAssignContext" :key="singleAssignContext.operationGeneration" :project-id="singleAssignContext.projectId" :operation-generation="singleAssignContext.operationGeneration" :shot="singleAssignContext.shot" :members="members" @close="closeSingleAssign" @assigned="handleSingleAssigned" @refresh="refreshSingleAssign" />
    <ShotImportDialog v-if="showImport && importProjectId && importOperationGeneration" :project-id="importProjectId" :operation-generation="importOperationGeneration" :project-name="project?.projectName" @close="closeImportDialog" @imported="handleImported" />
    <EpisodeSceneCreateDialog v-if="showHierarchyCreate && currentProjectId" :project-id="currentProjectId" :mode="hierarchyCreateMode" :episodes="episodes" :initial-episode-id="query.episodeId" @close="closeHierarchyCreate" @saved="handleHierarchySaved" />
    <el-dialog v-model="showBatchAssign" class="shot-batch-assign-dialog" :title="batchAssignLabel" width="520px" append-to-body :close-on-click-modal="!assigning" :close-on-press-escape="!assigning" :show-close="!assigning" @closed="resetBatchAssignForm">
      <el-form ref="batchAssignFormRef" :model="batchAssignForm" :rules="batchAssignRules" class="batch-assign-form" label-position="top" aria-label="镜头批量分配表单">
        <div class="batch-assign-summary"><strong>已选择 {{ selectedShots.length }} 个镜头</strong><span v-if="hasAssignedSelection">其中包含已分配镜头，确认后将改派到新的制作人。</span><span v-else>确认后将为所选镜头创建制作任务。</span></div>
        <el-form-item label="新的制作人" prop="assigneeUserId" required><el-select v-model="batchAssignForm.assigneeUserId" placeholder="请选择项目制作人员" aria-label="批量分配制作人" :disabled="assigning"><el-option v-for="member in creatorMembers" :key="member.userId" :label="shotAssigneeOptionLabel(member)" :value="String(member.userId)" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button :disabled="assigning" @click="closeBatchAssignDialog()">取消</el-button><el-button type="primary" :loading="assigning" :disabled="assigning" @click="confirmBatchAssign">确认{{ hasAssignedSelection ? '重新分配' : '分配' }}</el-button></template>
    </el-dialog>
    <el-drawer v-model="showDetail" class="sg-detail-drawer shot-detail-drawer" modal-class="sg-detail-drawer-mask" header-class="sg-detail-drawer__header" body-class="sg-detail-drawer__body" :title="detailDrawerTitle" direction="rtl" size="72%" resizable append-to-body destroy-on-close @closed="clearDetailDrawer">
      <ShotDetailView v-if="detailShotId && currentProjectId" embedded :target-project-id="currentProjectId" :target-shot-id="detailShotId" @changed="handleDetailChanged" @deleted="handleDetailDeleted" />
    </el-drawer>
  </section>
</template>

<style scoped>
.shot-card__media{position:relative}
.shot-directory-status{height:16px;padding:0 5px;font-size:10px;line-height:1}
.shot-list-toolbar>.shot-list-toolbar__summary{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:0;background:transparent;border:0}.shot-list-toolbar__summary>strong{color:var(--sg-text);font-size:23px;line-height:1}.shot-list-toolbar__summary>span{color:var(--sg-text-muted);font-size:11px}.shot-list-toolbar__summary:deep(.el-button){margin-left:0}.batch-assign-summary{display:grid;gap:6px;margin-bottom:20px;padding:14px;color:var(--sg-text-secondary);background:var(--sg-accent-soft);border-radius:10px}.batch-assign-summary strong{color:var(--sg-text)}.batch-assign-summary span{font-size:12px;line-height:1.5}.batch-assign-form:deep(.el-form-item){margin-bottom:0}.batch-assign-form:deep(.el-select){width:100%}.shot-selection{width:15px;height:15px;cursor:pointer}.shot-selection:disabled{cursor:not-allowed;opacity:.35}.shot-row-actions{display:flex;gap:2px;align-items:center;white-space:nowrap}.shot-long-text{line-height:1.55;white-space:pre-wrap}.shot-identity strong,.shot-identity small,.shot-parameters span,.shot-parameters small{display:block}.shot-identity small,.shot-parameters small{margin-top:5px;color:var(--sg-text-muted)}.shot-assets{display:flex;gap:5px;align-items:flex-start;flex-direction:column}.shot-assets__empty{color:var(--sg-text-muted)}.shot-status{display:grid;gap:5px;justify-items:start}
.shot-page{position:relative}.shot-heading__actions{display:flex;gap:10px}.project-context{display:flex;gap:16px;align-items:end;margin-bottom:14px;padding:16px;background:linear-gradient(90deg,rgba(255,182,87,.06),transparent),var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.project-context label{display:grid;min-width:280px;gap:6px}.project-context label>span{color:var(--sg-text-muted);font-size:10px}select,input{color:var(--sg-text);background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:9px}select{height:40px;padding:0 10px}.shot-filters{display:grid;grid-template-columns:minmax(240px,1.6fr) repeat(4,minmax(130px,.7fr)) auto auto;gap:9px;margin-bottom:14px;padding:14px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.shot-search{display:flex;height:40px;gap:8px;align-items:center;padding:0 11px;background:var(--sg-surface-soft);border:1px solid var(--sg-border);border-radius:9px}.shot-search input{min-width:0;flex:1;background:transparent;border:0;outline:0}.shot-list-toolbar{display:flex;align-items:center;justify-content:space-between;margin:0 2px 12px;color:var(--sg-text-muted);font-size:12px}.shot-list-toolbar>div{display:flex;gap:5px;padding:4px;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:9px}.shot-list-toolbar button{display:flex;gap:5px;align-items:center;padding:7px 9px;color:var(--sg-text-muted);cursor:pointer;background:transparent;border:0;border-radius:6px}.shot-list-toolbar button.active{color:var(--sg-accent);background:var(--sg-accent-soft)}.shot-loading,.shot-empty{display:grid;min-height:320px;place-items:center;align-content:center;padding:30px;color:var(--sg-text-muted);background:var(--sg-surface);border:1px dashed var(--sg-border-strong);border-radius:var(--sg-radius-lg)}.shot-empty>.el-icon{color:var(--sg-accent);font-size:34px}.shot-empty h3,.shot-empty p{margin:12px 0 0}.shot-empty p{max-width:600px;font-size:12px;text-align:center}.shot-table-wrap{overflow:hidden;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md)}.shot-data-table{--el-table-text-color:var(--sg-text-secondary);--el-table-header-text-color:var(--sg-text-muted);--el-table-border-color:var(--sg-border);width:100%}.shot-data-table:deep(.el-table__cell){padding:12px 0;font-size:11px}.shot-data-table:deep(th.el-table__cell){font-weight:650}.shot-description{line-height:1.55}.feedback-cell{line-height:1.55}.shot-thumb{position:relative;overflow:hidden;aspect-ratio:16/9;background:var(--sg-surface-soft);border-radius:10px}.shot-thumb img{width:100%;height:100%;object-fit:cover}.shot-thumb>div{display:grid;width:100%;height:100%;gap:5px;color:var(--sg-text-muted);place-items:center;align-content:center}.shot-thumb--small{width:90px}.shot-thumb--small>.el-icon{position:absolute;top:50%;left:50%;color:var(--sg-text-muted);font-size:20px;transform:translate(-50%,-50%)}.shot-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.shot-card{padding:12px;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:transform .15s,border-color .15s}.shot-card:hover,.shot-card:focus-visible,.story-frame:hover,.story-frame:focus-visible{border-color:rgba(255,182,87,.35);outline:0;transform:translateY(-2px)}.shot-card__duration{position:absolute;right:8px;bottom:8px;padding:4px 6px;color:white;font-size:10px;background:rgba(0,0,0,.72);border-radius:5px}.shot-card header,.shot-card footer{display:flex;gap:10px;align-items:center;justify-content:space-between}.shot-card header{margin-top:13px}.shot-card h3,.shot-card small,.shot-card p{margin:0}.shot-card h3{margin-top:3px;font-size:18px}.shot-card small,.shot-card footer{color:var(--sg-text-muted);font-size:10px}.shot-card>p{min-height:44px;margin:11px 0;color:var(--sg-text-secondary);font-size:12px;line-height:1.55}.storyboard{display:grid;gap:10px}.story-frame{display:grid;grid-template-columns:45px 230px 1fr;gap:14px;align-items:center;padding:10px;cursor:pointer;background:var(--sg-surface);border:1px solid var(--sg-border);border-radius:var(--sg-radius-md);transition:transform .15s,border-color .15s}.story-frame__index{color:var(--sg-accent);font-size:12px;font-weight:800;text-align:center}.story-frame p{margin:7px 0;color:var(--sg-text-secondary);font-size:12px}.story-frame small{color:var(--sg-text-muted)}.is-refreshing{opacity:.55}.shot-pagination{display:flex;gap:14px;align-items:center;justify-content:center;margin-top:20px;color:var(--sg-text-muted);font-size:12px}@media(max-width:1180px){.shot-filters{grid-template-columns:repeat(3,minmax(0,1fr))}.shot-search{grid-column:span 2}.shot-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.project-context{align-items:stretch;flex-direction:column}}@media(max-width:760px){.shot-filters,.shot-grid{grid-template-columns:1fr}.shot-search{grid-column:auto}.story-frame{grid-template-columns:35px 120px 1fr}.project-context label{min-width:0}}
.shot-list-toolbar>.shot-list-toolbar__summary{gap:8px;padding:0;background:transparent;border:0;border-radius:0}.shot-list-toolbar>.shot-list-toolbar__summary .el-button{margin-left:0;padding:8px 15px;color:inherit;background:transparent;border-radius:4px}.shot-list-toolbar>.shot-list-toolbar__summary .el-button--primary{color:var(--el-color-primary)}.shot-list-toolbar>.shot-list-toolbar__summary .el-button--danger{color:var(--el-color-danger)}
.project-context:deep(.el-form-item){min-width:280px;margin:0}.project-context:deep(.el-form-item__label){height:auto;padding-bottom:6px;color:var(--sg-text-muted);font-size:10px;line-height:1}.shot-filters .shot-search{height:auto;padding:0;background:transparent;border:0}.shot-search:deep(.el-input__wrapper){min-height:40px;background:var(--sg-surface-soft);box-shadow:0 0 0 1px var(--sg-border) inset}.shot-list-toolbar__views{padding:0!important;background:transparent!important}.shot-list-toolbar__views:deep(.el-radio-button__inner){display:flex;gap:6px;align-items:center;color:var(--sg-text-muted);background:var(--sg-surface);border-color:var(--sg-border);box-shadow:none}.shot-list-toolbar__views:deep(.el-radio-button__original-radio:checked+.el-radio-button__inner){color:var(--sg-accent);background:var(--sg-accent-soft);border-color:rgba(255,182,87,.32);box-shadow:-1px 0 0 0 rgba(255,182,87,.32)}.shot-card{padding:0}.shot-card:deep(.el-card__body){padding:12px}.shot-card:deep(.el-card__body)>p{min-height:44px;margin:11px 0;color:var(--sg-text-secondary);font-size:12px;line-height:1.55}.story-frame{display:block;padding:0}.story-frame:deep(.el-card__body){display:grid;grid-template-columns:45px 230px minmax(0,1fr);gap:14px;align-items:center;padding:10px}.shot-pagination{margin-top:20px}.shot-pagination:deep(.el-pager li),.shot-pagination:deep(button){background:var(--sg-surface)!important}.shot-pagination:deep(.is-active){color:#17130d!important;background:var(--sg-accent)!important}@media(max-width:760px){.story-frame:deep(.el-card__body){grid-template-columns:35px 120px minmax(0,1fr)}}
.shot-filters{grid-template-columns:minmax(240px,1.6fr) repeat(4,minmax(110px,.7fr)) auto}
.shot-filters:deep(.el-form-item){min-width:0;margin-bottom:0}
.shot-filter-item:deep(.el-form-item__content),.shot-filter-item:deep(.el-select),.shot-filter-item:deep(.el-input){width:100%;min-width:0}
.shot-filter-actions:deep(.el-form-item__content){flex-wrap:nowrap;justify-content:flex-end}
@media(max-width:1180px){.shot-filters{grid-template-columns:repeat(3,minmax(0,1fr))}.shot-filter-item--keyword{grid-column:span 2}.shot-filter-actions:deep(.el-form-item__content){justify-content:flex-start}}
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

.shot-drag-handle {
  color: var(--sg-text-muted);
  cursor: grab;
  font-size: 16px;
}

.shot-drag-handle:active { cursor: grabbing; }
.shot-drag-handle.is-disabled { color: var(--sg-border-strong); cursor: not-allowed; opacity: .55; }

.shot-data-table:deep(.shot-row--ghost td.el-table__cell) {
  background: var(--sg-accent-soft);
}

.shot-data-table:deep(.shot-row--chosen td.el-table__cell) {
  box-shadow: inset 0 1px 0 rgba(255,182,87,.35), inset 0 -1px 0 rgba(255,182,87,.35);
}
.shot-row-actions { flex-wrap: wrap; gap: 4px; white-space: normal; }
.shot-row-actions :deep(.el-button) { margin-left: 0; }
.task-date-cell { white-space: nowrap; font-variant-numeric: tabular-nums; }
</style>
