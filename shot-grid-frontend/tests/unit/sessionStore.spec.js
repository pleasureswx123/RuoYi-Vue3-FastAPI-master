import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCaptcha, getCurrentUser, login, logout } from '@/api/platform/auth'
import { getShotGridNavigation } from '@/api/shot-grid/navigation'
import { useSessionStore } from '@/store/modules/session'
import { ApiError } from '@/utils/apiError'
import { setToken } from '@/utils/auth'

vi.mock('@/api/platform/auth', () => ({
  getCaptcha: vi.fn(),
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn()
}))
vi.mock('@/api/shot-grid/navigation', () => ({ getShotGridNavigation: vi.fn() }))

const navigation = [
  { routeKey: 'workbench', title: '工作台', path: '/workbench', icon: 'dashboard', orderNum: 1 },
  { routeKey: 'projects', title: '项目', path: '/projects', icon: 'project', orderNum: 2 }
]

describe('独立业务端会话状态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    login.mockResolvedValue({ code: 200, token: 'token-1' })
    getCurrentUser.mockResolvedValue({
      code: 200,
      user: {
        userId: 7,
        userName: 'creator',
        nickName: '制作人',
        password: 'must-never-enter-the-store',
        phonenumber: '13800000000',
        dept: { deptId: 2, deptName: '策划部', ancestors: '0,1' }
      },
      roles: ['creator'],
      permissions: ['shotgrid:project:list']
    })
    getShotGridNavigation.mockResolvedValue({ code: 200, data: navigation })
    logout.mockResolvedValue({ code: 200 })
  })

  it('登录后只保存安全用户投影并只初始化一次', async () => {
    const session = useSessionStore()

    await session.signIn({ username: ' creator ', password: 'secret', code: '1234' })
    await Promise.all([session.bootstrap(), session.bootstrap()])

    expect(session.user).toEqual({
      userId: 7,
      userName: 'creator',
      nickName: '制作人',
      avatar: '',
      dept: { deptId: 2, deptName: '策划部' }
    })
    expect(session.user.password).toBeUndefined()
    expect(session.user.phonenumber).toBeUndefined()
    expect(getCurrentUser).toHaveBeenCalledTimes(1)
    expect(getShotGridNavigation).toHaveBeenCalledTimes(1)
  })

  it('退出接口失败也清理本地登录态', async () => {
    const session = useSessionStore()
    await session.signIn({ username: 'creator', password: 'secret' })
    logout.mockRejectedValueOnce(new Error('服务端退出失败'))

    await expect(session.signOut()).rejects.toThrow('服务端退出失败')
    expect(session.token).toBe('')
    expect(session.user).toBeNull()
  })

  it('加载验证码时保留后端开关', async () => {
    getCaptcha.mockResolvedValue({ captchaEnabled: false, img: '', uuid: '' })
    const session = useSessionStore()

    await session.loadCaptcha()

    expect(session.captcha).toMatchObject({ enabled: false, image: '', uuid: '' })
  })

  it('用户响应缺少有效 userId 时失败关闭并清理会话', async () => {
    getCurrentUser.mockResolvedValueOnce({ user: null, roles: [], permissions: [] })
    const session = useSessionStore()

    await expect(session.signIn({ username: 'creator', password: 'secret' })).rejects.toMatchObject({
      status: 401,
      errorKey: 'SG_CURRENT_USER_INVALID'
    })
    expect(session.token).toBe('')
    expect(session.status).toBe('anonymous')
  })

  it('初始化失败只缓存不含 Authorization 的安全错误摘要', async () => {
    setToken('token-1')
    getCurrentUser.mockRejectedValueOnce(
      new ApiError('服务异常', {
        status: 503,
        code: 503,
        errorKey: 'SG_SERVICE_UNAVAILABLE',
        response: { config: { headers: { Authorization: 'Bearer secret-token' } } }
      })
    )
    const session = useSessionStore()

    await expect(session.bootstrap()).rejects.toMatchObject({ status: 503 })

    expect(session.bootstrapError).toEqual({
      status: 503,
      httpStatus: null,
      code: 503,
      errorKey: 'SG_SERVICE_UNAVAILABLE',
      message: '服务异常'
    })
    expect(JSON.stringify(session.bootstrapError)).not.toContain('secret-token')
  })
})
