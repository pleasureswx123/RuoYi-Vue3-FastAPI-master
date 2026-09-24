import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import VersionWorkspace from '@/components/version/VersionWorkspace.vue'
import { useSessionStore } from '@/store/modules/session'

const historyStub = {
  name: 'VersionHistoryPanel',
  methods: { focusIssue() {} },
  template: '<div data-testid="version-history" />'
}

const submissionStub = {
  name: 'VersionSubmissionPanel',
  template: '<div data-testid="version-submission" />'
}

function mountWorkspace({
  taskStatus = 'not_started',
  taskKind = 'shot_video',
  allowedActions = [],
  hasUncommittedSubmission = false,
  permissions = []
} = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.permissions = permissions

  return mount(VersionWorkspace, {
    props: {
      taskId: 31,
      taskKind,
      taskStatus,
      allowedActions,
      hasUncommittedSubmission
    },
    global: {
      plugins: [pinia],
      stubs: {
        VersionHistoryPanel: historyStub,
        VersionSubmissionPanel: submissionStub
      }
    }
  })
}

describe('版本工作区提交入口', () => {
  it.each([
    ['shot_video', 'not_started'],
    ['shot_video', 'preparing'],
    ['asset_image', 'not_started'],
    ['asset_image', 'preparing']
  ])('%s 的 %s 任务即使响应误带提交动作也仅显示版本历史', (taskKind, taskStatus) => {
    const wrapper = mountWorkspace({
      taskKind,
      taskStatus,
      allowedActions: ['version.add'],
      permissions: ['shotgrid:version:add']
    })

    expect(wrapper.find('[data-testid="version-history"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="version-submission"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('任务待审核时保留追加和未完成提交恢复入口', () => {
    const wrapper = mountWorkspace({
      taskStatus: 'pending_review',
      allowedActions: ['version.add'],
      hasUncommittedSubmission: true,
      permissions: ['shotgrid:version:add']
    })

    expect(wrapper.find('[data-testid="version-history"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="version-submission"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('追加表单仅在最新待审核版本显示，切换历史时隐藏且保留实例', async () => {
    const wrapper = mountWorkspace({ taskStatus: 'pending_review', allowedActions: ['version.add'], permissions: ['shotgrid:version:add'] })
    await wrapper.setProps({ latestVersionNo: 2 })
    const history = wrapper.findComponent(historyStub)
    const submission = wrapper.findComponent(submissionStub)
    const context = { taskId: 31, operationGeneration: 0 }
    expect(submission.isVisible()).toBe(false)
    history.vm.$emit('version-selected', { versionNo: 2, versionStatus: 'pending_review' }, context)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="version-submission"]').attributes('style')).not.toContain('display: none')
    history.vm.$emit('selection-loading')
    await wrapper.vm.$nextTick()
    expect(submission.isVisible()).toBe(false)
    history.vm.$emit('version-selected', { versionNo: 1, versionStatus: 'rejected' }, context)
    await wrapper.vm.$nextTick()
    expect(submission.isVisible()).toBe(false)
    history.vm.$emit('version-selected', { versionNo: 2, versionStatus: 'pending_review' }, context)
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(submissionStub).vm).toBe(submission.vm)
    expect(wrapper.get('[data-testid="version-submission"]').attributes('style')).not.toContain('display: none')
    wrapper.unmount()
  })

  it('后端动作与平台权限同时允许时显示提交入口', () => {
    const wrapper = mountWorkspace({
      taskStatus: 'in_progress',
      allowedActions: ['version.add'],
      permissions: ['shotgrid:version:add']
    })

    expect(wrapper.find('[data-testid="version-submission"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('存在未完成提交时保留恢复入口', () => {
    const wrapper = mountWorkspace({ taskStatus: 'in_progress', hasUncommittedSubmission: true })

    expect(wrapper.find('[data-testid="version-submission"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
