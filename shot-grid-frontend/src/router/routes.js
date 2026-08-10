import AppLayout from '@/layout/AppLayout.vue'

export const stableRoutes = [
  { path: '/login', name: 'Login', component: () => import('@/views/auth/LoginView.vue'), meta: { public: true } },
  { path: '/session-expired', name: 'SessionExpired', component: () => import('@/views/error/SessionExpiredView.vue'), meta: { public: true } },
  { path: '/403', name: 'Forbidden', component: () => import('@/views/error/ForbiddenView.vue'), meta: { public: true } },
  { path: '/feature-unavailable', name: 'FeatureUnavailable', component: () => import('@/views/error/FeatureUnavailableView.vue'), meta: { public: true } },
  { path: '/service-error', name: 'ServiceError', component: () => import('@/views/error/ServiceErrorView.vue'), meta: { public: true } },
  {
    path: '/', component: AppLayout, redirect: '/workbench', children: [
      { path: 'workbench', name: 'Workbench', component: () => import('@/views/workbench/WorkbenchView.vue'), meta: { navigationKey: 'workbench' } },
      { path: 'projects', name: 'Projects', component: () => import('@/views/project/index.vue'), meta: { navigationKey: 'projects' } },
      { path: 'shots', name: 'Shots', component: () => import('@/views/shot/ShotListView.vue'), meta: { navigationKey: 'shots' } },
      { path: 'assets', name: 'Assets', component: () => import('@/views/asset/AssetListView.vue'), meta: { navigationKey: 'assets' } },
      { path: 'reviews', name: 'Reviews', component: () => import('@/views/review/ReviewListView.vue'), meta: { navigationKey: 'reviews' } },
      { path: 'files', name: 'Files', component: () => import('@/views/file/FileView.vue'), meta: { navigationKey: 'files' } },
      { path: 'projects/:projectId/overview', name: 'ProjectOverview', component: () => import('@/views/project/ProjectOverviewView.vue'), props: true, meta: { navigationKey: 'projects' } },
      { path: 'projects/:projectId/scenes', name: 'ProjectScenes', component: () => import('@/views/project/ProjectSectionView.vue'), props: true, meta: { navigationKey: 'projects', section: '场次' } },
      { path: 'projects/:projectId/shots', name: 'ProjectShots', component: () => import('@/views/project/ProjectSectionView.vue'), props: true, meta: { navigationKey: 'shots', section: '镜头' } },
      { path: 'projects/:projectId/assets', name: 'ProjectAssets', component: () => import('@/views/project/ProjectSectionView.vue'), props: true, meta: { navigationKey: 'assets', section: '资产' } },
      { path: 'projects/:projectId/reviews', name: 'ProjectReviews', component: () => import('@/views/project/ProjectSectionView.vue'), props: true, meta: { navigationKey: 'reviews', section: '审核' } },
      { path: 'projects/:projectId/members', name: 'ProjectMembers', component: () => import('@/views/project/ProjectMembersView.vue'), props: true, meta: { navigationKey: 'projects', section: '成员' } },
      { path: 'shots/:shotId', name: 'ShotDetail', component: () => import('@/views/shot/ShotDetailView.vue'), props: true, meta: { navigationKey: 'shots' } },
      { path: 'assets/:assetId', name: 'AssetDetail', component: () => import('@/views/asset/AssetDetailView.vue'), props: true, meta: { navigationKey: 'assets' } },
      { path: 'tasks/:taskId', name: 'TaskDetail', component: () => import('@/views/task/TaskDetailView.vue'), props: true, meta: { navigationKey: 'workbench' } },
      { path: 'versions/:versionId/review', name: 'VersionReview', component: () => import('@/views/review/VersionReviewView.vue'), props: true, meta: { navigationKey: 'reviews' } }
    ]
  },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/error/NotFoundView.vue'), meta: { public: true } }
]
