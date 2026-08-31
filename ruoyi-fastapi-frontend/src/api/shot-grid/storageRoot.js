import request from '@/utils/request'

// 查询 NAS 根目录配置
export function listStorageRoots(query) {
  return request({
    url: '/shot-grid/admin/storage-roots',
    method: 'get',
    params: query
  })
}

// 查询 NAS 根目录详情
export function getStorageRoot(storageRootId) {
  return request({
    url: `/shot-grid/admin/storage-roots/${storageRootId}`,
    method: 'get'
  })
}

// 新增 NAS 根目录配置
export function addStorageRoot(data) {
  return request({
    url: '/shot-grid/admin/storage-roots',
    method: 'post',
    data
  })
}

// 修改或启停 NAS 根目录配置
export function updateStorageRoot(storageRootId, data) {
  return request({
    url: `/shot-grid/admin/storage-roots/${storageRootId}`,
    method: 'put',
    data
  })
}

// 删除平台中的 NAS 根目录配置，不删除实际目录或文件
export function deleteStorageRoot(storageRootId, data) {
  return request({
    url: `/shot-grid/admin/storage-roots/${storageRootId}`,
    method: 'delete',
    data
  })
}

// 由后端服务执行真实的 UNC 读写删除探测
export function probeStorageRoot(storageRootId) {
  return request({
    url: `/shot-grid/admin/storage-roots/${storageRootId}/probe`,
    method: 'post'
  })
}
