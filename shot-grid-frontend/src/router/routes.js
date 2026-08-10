import AppLayout from '@/layout/AppLayout.vue'

export const stableRoutes = [
  { path: '/login', name: 'Login', component: () => import('@/views/auth/LoginView.vue'), meta: { public: true } },
  { path: '/session-expired', name: 'SessionExpired', component: () => import('@/views/error/SessionExpiredView.vue'), meta: { public: true } },
  { path: '/403', name: 'Forbidden', component: () => import('@/views/error/ForbiddenView.vue'), meta: { public: true } },
  { path: '/service-error', name: 'ServiceError', component: () => import('@/views/error/ServiceErrorView.vue'), meta: { public: true } },
  {
    path: '/', component: AppLayout, redirect: '/workbench', children: [
      { path: 'workbench', name: 'Workbench', component: () => import('@/views/workbench/WorkbenchView.vue') },
      { path: 'projects', name: 'Projects', component: () => import('@/views/project/ProjectListView.vue') },
      { path: 'projects/:projectId/overview', name: 'ProjectOverview', component: () => import('@/views/project/ProjectOverviewView.vue'), props: true },
      { path: 'files', name: 'Files', component: () => import('@/views/file/FileView.vue') }
    ]
  },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/error/NotFoundView.vue'), meta: { public: true } }
]
