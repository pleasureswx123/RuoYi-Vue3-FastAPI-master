import {
  ElAlert,
  ElButton,
  ElCard,
  ElCollapse,
  ElCollapseItem,
  ElDescriptions,
  ElDescriptionsItem,
  ElEmpty,
  ElIcon,
  ElSkeleton,
  ElStatistic,
  ElStep,
  ElSteps,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTabs,
  ElTimeline,
  ElTimelineItem
} from 'element-plus'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getProductionHistory } from '@/api/shot-grid/productionHistory'
import ProductionHistoryPanel from '@/components/production-history/ProductionHistoryPanel.vue'

vi.mock('@/api/shot-grid/productionHistory', () => ({ getProductionHistory: vi.fn() }))

const components = {
  ElAlert,
  ElButton,
  ElCard,
  ElCollapse,
  ElCollapseItem,
  ElDescriptions,
  ElDescriptionsItem,
  ElEmpty,
  ElIcon,
  ElSkeleton,
  ElStatistic,
  ElStep,
  ElSteps,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTabs,
  ElTimeline,
  ElTimelineItem
}

function summary(overrides = {}) {
  return {
    currentStage: 'revision',
    activeStep: 3,
    laneCount: 1,
    taskCount: 1,
    versionCount: 2,
    reviewActionCount: 2,
    rejectionCount: 1,
    issueCount: 1,
    openIssueCount: 0,
    resolvedIssueCount: 1,
    finalVersionCount: 0,
    ...overrides
  }
}

function task(taskId, assigneeName = '杨景锋') {
  return {
    taskId,
    taskName: `任务 ${taskId}`,
    taskKind: 'shot_video',
    taskStatus: 'revision',
    priority: 'normal',
    dueDate: '2026-08-22',
    assignee: { userId: 7, userName: assigneeName, nickName: 'YJF' },
    createTime: '2026-08-12T09:10:00',
    updateTime: '2026-08-14T10:00:00'
  }
}

function versionCycle(versionId = 91) {
  return {
    versionId,
    versionNo: 2,
    versionNumber: 'V002',
    versionStatus: 'rejected',
    changelog: '按 V001 审核意见调整运镜和色调。',
    submittedTime: '2026-08-14T09:00:00',
    submitter: { userId: 7, userName: '杨景锋', nickName: 'YJF' },
    primaryFile: {
      fileId: 'file-main',
      businessFileName: 'LCFR_EP001_000_S001_YJF_V002.mov',
      fileRole: 'review_media',
      isPrimary: true,
      contentType: 'video/quicktime',
      fileSize: 2048
    },
    thumbnailFile: null,
    autoReviewList: { reviewListId: 81, reviewListName: 'V002 自动审核单', reviewStatus: 'completed' },
    reviewActions: [{
      actionId: 71,
      actionType: 'reject',
      fromStatus: 'pending_review',
      toStatus: 'rejected',
      reason: '色调仍然偏冷。',
      reviewer: { userId: 1, userName: '项目管理人' },
      createTime: '2026-08-14T10:00:00'
    }],
    sourceIssues: [{
      issueId: 501,
      originVersionId: 90,
      originVersionNumber: 'V001',
      reviewer: { userId: 1, userName: '项目管理人' },
      content: null,
      mediaTimeMs: 6100,
      hasAnnotations: true,
      annotationCount: 2,
      status: 'resolved',
      resolvedInVersionId: 91,
      resolvedInVersionNumber: 'V002',
      createTime: '2026-08-13T10:00:00',
      updateTime: '2026-08-14T10:00:00'
    }],
    issueResponses: [{
      responseId: 601,
      issueId: 501,
      originVersionId: 90,
      originVersionNumber: 'V001',
      responseText: '增加稳定参数并重新输出。',
      responder: { userId: 7, userName: '杨景锋' },
      createTime: '2026-08-14T09:00:00'
    }],
    issueVerifications: [{
      verificationId: 701,
      issueId: 501,
      originVersionId: 90,
      originVersionNumber: 'V001',
      checkedVersionId: 91,
      checkedVersionNumber: 'V002',
      result: 'resolved',
      comment: null,
      reviewer: { userId: 1, userName: '项目管理人' },
      createTime: '2026-08-14T10:00:00'
    }]
  }
}

function shotHistory(subjectId = 41, laneName = 'S001') {
  return {
    subject: {
      subjectType: 'shot',
      subjectId,
      projectId: 8,
      projectCode: 'LCFR',
      projectName: '罗刹夫人',
      code: laneName,
      name: laneName,
      lifecycleStatus: 'active',
      createdAt: '2026-08-12T09:00:00'
    },
    summary: summary(),
    lanes: [{
      laneId: subjectId,
      laneType: 'shot',
      name: laneName,
      sortOrder: 10,
      lifecycleStatus: 'active',
      currentStage: 'revision',
      activeStep: 3,
      task: task(31),
      latestVersion: { versionId: 91, versionNo: 2, versionNumber: 'V002', versionStatus: 'rejected', submittedTime: '2026-08-14T09:00:00' },
      finalVersion: null,
      versionCount: 2,
      reviewActionCount: 2,
      rejectionCount: 1,
      issueCount: 1,
      openIssueCount: 0
    }],
    events: [
      {
        eventId: `subject:${subjectId}`,
        eventType: 'subject_created',
        occurredAt: '2026-08-12T09:00:00',
        evidenceLevel: 'confirmed',
        title: '镜头记录已创建',
        laneIds: [],
        actor: { userName: '项目管理人' },
        resourceRef: { resourceType: 'shot', resourceId: subjectId }
      },
      {
        eventId: 'task:31',
        eventType: 'task_created',
        occurredAt: '2026-08-12T09:10:00',
        evidenceLevel: 'inferred',
        title: '制作任务已建立',
        description: '当前负责人显示在阶段概览中。',
        laneIds: [subjectId],
        actor: null,
        resourceRef: { resourceType: 'task', resourceId: 31 }
      },
      {
        eventId: 'version:91',
        eventType: 'version_cycle',
        occurredAt: '2026-08-14T09:00:00',
        evidenceLevel: 'confirmed',
        title: '提交 V002',
        laneIds: [subjectId],
        actor: { userId: 7, userName: '杨景锋' },
        resourceRef: { resourceType: 'version', resourceId: 91 },
        versionCycle: versionCycle()
      }
    ]
  }
}

function assetHistory() {
  const firstLane = {
    ...shotHistory(1001, '主视角').lanes[0],
    laneId: 1001,
    laneType: 'assetItem',
    task: { ...task(51), taskKind: 'asset_image' }
  }
  const secondLane = {
    ...firstLane,
    laneId: 1002,
    name: '反打视角',
    task: { ...task(52, '庞晓亮'), taskId: 52 },
    lifecycleStatus: 'archived',
    versionCount: 1,
    rejectionCount: 0
  }
  return {
    subject: {
      subjectType: 'asset',
      subjectId: 31,
      projectId: 8,
      projectCode: 'LCFR',
      projectName: '罗刹夫人',
      name: '动力舱室内',
      lifecycleStatus: 'active',
      assetType: 'Environment',
      createdAt: '2026-08-12T09:00:00'
    },
    summary: summary({ laneCount: 2, taskCount: 2, versionCount: 3 }),
    lanes: [firstLane, secondLane],
    events: [
      {
        eventId: 'asset:31',
        eventType: 'subject_created',
        occurredAt: '2026-08-12T09:00:00',
        evidenceLevel: 'confirmed',
        title: '资产记录已创建',
        laneIds: [],
        actor: { userName: '项目管理人' },
        resourceRef: { resourceType: 'asset', resourceId: 31 }
      },
      {
        eventId: 'import:21',
        eventType: 'subject_imported',
        occurredAt: '2026-08-12T09:05:00',
        evidenceLevel: 'confirmed',
        title: '制作分项已导入',
        laneIds: [1001, 1002],
        actor: { userName: '项目管理人' },
        resourceRef: { resourceType: 'importBatch', resourceId: 21 },
        importBatch: {
          batchId: 21,
          originalFileName: '资产制作分项.xlsx',
          importType: 'asset',
          batchStatus: 'committed',
          committedTime: '2026-08-12T09:05:00'
        }
      },
      {
        eventId: 'task:51',
        eventType: 'task_created',
        occurredAt: '2026-08-12T09:10:00',
        evidenceLevel: 'inferred',
        title: '主视角任务已建立',
        laneIds: [1001],
        actor: null,
        resourceRef: { resourceType: 'task', resourceId: 51 }
      },
      {
        eventId: 'task:52',
        eventType: 'task_created',
        occurredAt: '2026-08-12T09:20:00',
        evidenceLevel: 'inferred',
        title: '反打视角任务已建立',
        laneIds: [1002],
        actor: null,
        resourceRef: { resourceType: 'task', resourceId: 52 }
      }
    ]
  }
}

async function mountPanel(props = { projectId: 8, subjectId: 41, subjectType: 'shot' }) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workbench', name: 'workbench', component: { template: '<div />' } },
      { path: '/tasks/:taskId', name: 'task-detail', component: { template: '<div />' } },
      { path: '/versions/:versionId', name: 'version-detail', component: { template: '<div />' } },
      { path: '/reviews/:reviewListId', name: 'review-detail', component: { template: '<div />' } },
      { path: '/projects/:projectId/shots/:shotId', name: 'shot-detail', component: { template: '<div />' } },
      { path: '/projects/:projectId/assets/:assetId', name: 'asset-detail', component: { template: '<div />' } }
    ]
  })
  await router.push('/workbench')
  await router.isReady()
  const wrapper = mount(ProductionHistoryPanel, {
    props,
    global: { plugins: [router], components }
  })
  await flushPromises()
  return { wrapper, router }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('制作履历面板', () => {
  beforeEach(() => {
    getProductionHistory.mockReset()
    getProductionHistory.mockResolvedValue({ data: shotHistory() })
  })

  it('用六步总览和版本主节点展示真实审核闭环，并提供任务、版本与审核单深链', async () => {
    const { wrapper, router } = await mountPanel()

    expect(getProductionHistory).toHaveBeenCalledWith(8, 'shot', 41, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.findAllComponents(ElStep).map(step => step.props('title'))).toEqual(['创建/导入', '委派', '制作', '提交版本', '审核', '完成'])
    expect(wrapper.findComponent(ElSteps).props()).toMatchObject({ active: 2, alignCenter: true, finishStatus: 'success' })
    expect(wrapper.findComponent(ElSteps).attributes('aria-label')).toBe('制作阶段')
    expect(wrapper.findAllComponents(ElTimelineItem).every(item => item.props('size') === 'large')).toBe(true)
    expect(wrapper.findAllComponents(ElTimelineItem).some(item => item.props('hollow') === true)).toBe(true)
    expect(wrapper.text()).toContain('没有独立审计证据的动作不会被补写')
    expect(wrapper.text()).toContain('返修中')
    expect(wrapper.text()).toContain('当前负责人：杨景锋')
    expect(wrapper.text()).toContain('按现有记录推断')
    expect(wrapper.text()).toContain('V002')
    const detailTitles = wrapper.findAll('.version-cycle__detail-title').map(item => item.text())
    expect(detailTitles).toEqual(['审核动作1 条', '修改问题1 条', '制作处理说明1 条', '审核确认1 条'])
    expect(wrapper.text()).toContain('待审核 → 已退回')
    expect(wrapper.text()).toContain('包含 2 个画面标注。')
    expect(wrapper.findAllComponents(ElButton).some(button => button.text() === '查看镜头')).toBe(false)

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '查看任务').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value).toMatchObject({ name: 'task-detail', params: { taskId: '31' } })
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '版本详情').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value).toMatchObject({ name: 'version-detail', params: { versionId: '91' } })
    await wrapper.findAllComponents(ElButton).find(button => button.text() === '审核单').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value).toMatchObject({ name: 'review-detail', params: { reviewListId: '81' } })
    wrapper.unmount()
  })

  it('资产全部分项只显示汇总，切换后只呈现当前分项与全局事件', async () => {
    getProductionHistory.mockResolvedValue({ data: assetHistory() })
    const { wrapper } = await mountPanel({ projectId: 8, subjectId: 31, subjectType: 'asset' })

    expect(wrapper.findComponent(ElTabs).exists()).toBe(true)
    expect(wrapper.find('.history-lane-summary').text()).toContain('主视角')
    expect(wrapper.find('.history-lane-summary').text()).toContain('反打视角')
    expect(wrapper.find('.history-lane-summary').text()).toContain('已归档')
    expect(wrapper.find('.history-timeline').exists()).toBe(false)

    await wrapper.findAllComponents(ElButton).find(button => button.text() === '查看履历').trigger('click')
    await flushPromises()
    expect(wrapper.find('.history-timeline').text()).toContain('资产记录已创建')
    expect(wrapper.find('.history-timeline').text()).toContain('已提交')
    expect(wrapper.find('.history-timeline').text()).toContain('主视角任务已建立')
    expect(wrapper.find('.history-timeline').text()).not.toContain('反打视角任务已建立')
    wrapper.unmount()
  })

  it('切换对象时中止旧请求并用 generation 阻止迟到响应覆盖新履历', async () => {
    const first = deferred()
    const second = deferred()
    const signals = []
    getProductionHistory.mockImplementation((_projectId, _subjectType, _subjectId, options) => {
      signals.push(options.signal)
      return signals.length === 1 ? first.promise : second.promise
    })
    const { wrapper } = await mountPanel()
    await wrapper.setProps({ subjectId: 42 })
    expect(signals[0].aborted).toBe(true)

    second.resolve({ data: shotHistory(42, 'S042') })
    await flushPromises()
    expect(wrapper.text()).toContain('S042')
    first.resolve({ data: shotHistory(41, 'S041') })
    await flushPromises()
    expect(wrapper.text()).toContain('S042')
    expect(wrapper.text()).not.toContain('S041')
    wrapper.unmount()
  })
})
