const prefix = '\\\\192.168.10.64\\'

export function validateNasFolder(path) {
  if (typeof path !== 'string' || path.length > 2000 || !path.startsWith(prefix)) throw new Error('仅支持公司 NAS 服务器 192.168.10.64')
  const parts = path.slice(prefix.length).split('\\')
  if (parts.length < 2 || parts.some(part => !part || Array.from(part).some(char => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127) || /[<>:"/|?*%]/.test(part) || /[. ]$/.test(part) || part === '.' || part === '..' || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part)) || parts[0].endsWith('$')) {
    throw new Error('NAS 目录格式不安全或不完整')
  }
  return path
}

export function versionNasFolders(version, target) {
  if (Number(version?.projectId) !== target.projectId || Number(version?.taskId) !== target.taskId || Number(version?.versionId) !== target.versionId) throw new Error('版本归属已变化，请刷新列表后重试')
  const folders = new Set()
  for (const file of version.files || []) {
    if (!file.nasPath || ['thumbnail', 'proxy_media'].includes(file.role)) continue
    // 先校验完整文件路径，防止非法文件名被截去后掩盖问题。
    validateNasFolder(file.nasPath)
    folders.add(validateNasFolder(file.nasPath.slice(0, file.nasPath.lastIndexOf('\\'))))
  }
  return [...folders]
}
