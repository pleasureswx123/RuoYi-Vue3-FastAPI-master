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
      taskKind: 'shot_video',
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
  it('任务未开始时即使响应误带提交动作也仅显示版本历史', () => {
    const wrapper = mountWorkspace({
      allowedActions: ['version.add'],
      permissions: ['shotgrid:version:add']
    })

    expect(wrapper.find('[data-testid="version-history"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="version-submission"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('任务待审核时即使存在提交动作或未完成标记也不显示提交入口', () => {
    const wrapper = mountWorkspace({
      taskStatus: 'pending_review',
      allowedActions: ['version.add'],
      hasUncommittedSubmission: true,
      permissions: ['shotgrid:version:add']
    })

    expect(wrapper.find('[data-testid="version-history"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="version-submission"]').exists()).toBe(false)
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
