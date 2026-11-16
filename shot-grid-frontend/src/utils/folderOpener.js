// 与 Windows 打开器保持同一服务器边界；不接受本机路径、设备路径或命令。
export function validNasFolder(value) {
  if (typeof value !== 'string' || value.length > 2048 || !value.startsWith('\\\\192.168.10.64\\')) return false
  const parts = value.slice(2).split('\\')
  return parts.length >= 2 && parts.every(part => part && part !== '.' && part !== '..' &&
    part === part.trim() && !part.endsWith('.') &&
    !Array.from(part).some(char => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127 || '/:*?"<>|'.includes(char)) &&
    !/^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)/i.test(part))
}

export function candidateFolderPath(files) {
  // 只取当前候选的原始成果，派生缩略图或代理视频不是原文件所在目录。
  const file = files?.find(item => item.role === 'review_media')
  const path = file?.nasPath
  if (!validNasFolder(path)) return ''
  const folder = path.slice(0, path.lastIndexOf('\\'))
  return validNasFolder(folder) ? folder : ''
}

export function folderProtocolUrl(folder) {
  if (!validNasFolder(folder)) return ''
  const bytes = new TextEncoder().encode(folder)
  const encoded = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `shotgrid-folder://open/${encoded}`
}

// 服务器只提供项目内相对目录；打开器再复核并限定在已配置的本地模拟根内。
export function localLayoutFolderUrl(relative) {
  if (typeof relative !== 'string' || relative.length > 1024) return ''
  const parts = relative.split('\\')
  if (parts.at(-1) === 'FINAL') parts.pop()
  if (!validNasFolder('\\\\192.168.10.64\\demo\\' + relative)) return ''
  const [, kind, episodeOrType, , item, version] = parts
  const legacy = parts.length === 4 && (kind === 'VIDEO' || kind === 'ASSET')
  const versioned = parts.length === 6 && /^V[0-9]{3,}$/.test(version) && (
    (kind === 'SHOT' && /^EP[0-9]{2,}$/i.test(episodeOrType) && /^[0-9]{3,}$/.test(parts[3]) && /^[0-9]{4,}$/.test(item)) ||
    (kind === 'ASSET' && /^(character|environment|prop)$/i.test(episodeOrType) && /.+__[1-9][0-9]*$/.test(item))
  )
  if (!legacy && !versioned) return ''
  const encoded = btoa(String.fromCharCode(...new TextEncoder().encode(relative))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `shotgrid-folder://demo-layout/${encoded}`
}

// 本机开发演示只传实体编号，实际目录由已安装打开器的本地配置决定。
export function localDemoFolderUrl(projectId, shotId, versionId, candidateId = 0, assetId = 0) {
  const ids = [projectId, shotId, versionId, candidateId]
  if (!ids.every((id, index) => Number.isSafeInteger(id) && id >= (index === 3 ? 0 : 1))) return ''
  if (assetId !== 0) {
    if (!Number.isSafeInteger(assetId) || assetId < 1) return ''
    return `shotgrid-folder://demo-asset/${projectId}/${assetId}/${shotId}/${versionId}/${candidateId}`
  }
  return `shotgrid-folder://demo/${ids.join('/')}`
}

export function requestLocalDemoFolder(projectId, shotId, versionId, candidateId = 0, assetId = 0, relative = '') {
  const identity = localDemoFolderUrl(projectId, shotId, versionId, candidateId, assetId)
  const url = identity && (relative ? localLayoutFolderUrl(relative) : identity)
  if (!url) return false
  const link = document.createElement('a')
  link.href = url
  link.hidden = true
  document.body.appendChild(link)
  try { link.click(); return true } finally { link.remove() }
}
