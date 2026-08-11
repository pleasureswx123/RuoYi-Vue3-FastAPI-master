import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/login/LoginView.vue'),
    meta: { public: true, title: '登录' }
  },
  {
    path: '/service-unavailable',
    name: 'service-unavailable',
    component: () => import('@/views/error/ServiceUnavailableView.vue'),
    meta: { public: true, title: '服务暂不可用' }
  },
  {
    path: '/forbidden',
    name: 'forbidden',
    component: () => import('@/views/error/ForbiddenView.vue'),
    meta: { public: true, title: '无访问权限' }
  },
  {
    path: '/',
    name: 'root',
    component: () => import('@/layout/AppLayout.vue'),
    children: [
      {
        path: 'workbench',
        name: 'workbench',
        component: () => import('@/views/workbench/WorkbenchView.vue'),
        meta: { title: '工作台', routeKey: 'workbench' }
      },
      {
        path: 'tasks/:taskId',
        name: 'task-detail',
        component: () => import('@/views/task/TaskDetailView.vue'),
        meta: { title: '任务详情', routeKey: 'workbench' }
      },
      {
        path: 'versions/:versionId',
        name: 'version-detail',
        component: () => import('@/views/version/VersionDetailView.vue'),
        meta: { title: '版本详情', routeKey: 'reviews' }
      },
      {
        path: 'projects',
        name: 'projects',
        component: () => import('@/views/project/ProjectListView.vue'),
        meta: { title: '项目', routeKey: 'projects' }
      },
      {
        path: 'projects/:projectId/overview',
        name: 'project-overview',
        component: () => import('@/views/project/ProjectDetailView.vue'),
        meta: { title: '项目详情', routeKey: 'projects' }
      },
      {
        path: 'shots',
        name: 'shots',
        component: () => import('@/views/shot/ShotListView.vue'),
        meta: { title: '镜头管理', routeKey: 'shots' }
      },
      {
        path: 'projects/:projectId/shots/:shotId',
        name: 'shot-detail',
        component: () => import('@/views/shot/ShotDetailView.vue'),
        meta: { title: '镜头详情', routeKey: 'shots' }
      },
      {
        path: 'assets',
        name: 'assets',
        component: () => import('@/views/asset/AssetListView.vue'),
        meta: { title: '资产库管理', routeKey: 'assets' }
      },
      {
        path: 'projects/:projectId/assets/:assetId',
        name: 'asset-detail',
        component: () => import('@/views/asset/AssetDetailView.vue'),
        meta: { title: '资产详情', routeKey: 'assets' }
      },
      {
        path: 'reviews',
        name: 'reviews',
        component: () => import('@/views/review/ReviewListView.vue'),
        meta: { title: '版本审核', routeKey: 'reviews' }
      },
      {
        path: 'files',
        name: 'files',
        component: () => import('@/views/file/FileCenterView.vue'),
        meta: { title: '文件与 NAS', routeKey: 'files' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/error/NotFoundView.vue'),
    meta: { title: '页面不存在' }
  }
]

export function createShotGridRouter() {
  return createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes,
    scrollBehavior: () => ({ top: 0 })
  })
}

export default createShotGridRouter()
