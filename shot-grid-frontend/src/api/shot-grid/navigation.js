import request from '@/utils/request'

/** 只读取 Shot Grid 应用范围内的导航，不使用平台 /getRouters。 */
export const getShotGridNavigation = () => request({ url: '/shot-grid/navigation', method: 'get' })
