<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ElMessage, ElPopover } from 'element-plus'
import { FolderOpened, QuestionFilled } from '@element-plus/icons-vue'
import { getVersionDetail, getNasOpenTicket, getNasOpenerPublicKey, getProjectNasOpenTicket } from '@/api/shot-grid/versions'
import { getProjectStorage } from '@/api/shot-grid/projects'
import { copyTextToClipboard } from '@/utils/clipboard'
import { versionNasFolders, validateNasFolder } from '@/utils/nasExplorer'

const props = defineProps({ projectId: { type: Number, default: 0 }, canQuery: Boolean })
const menu = ref(false)
const visible = ref(false)
const anchor = shallowRef(null)
const target = shallowRef(null)
const loading = ref(false)
const error = ref('')
const folders = ref([])
const selected = ref('')
const attempted = ref(false)
const files = ref([])
const installing = ref(false)
const installer = `${import.meta.env.BASE_URL}tools/Install-ShotGridNas.ps1`
let controller
let generation = 0
function reset() {
  generation++
  controller?.abort()
  menu.value = false
  visible.value = false
  loading.value = false
  target.value = null
  attempted.value = false
}
watch(() => [props.projectId, props.canQuery], reset)
function dismissMenu(event) {
  if (event.type === 'keydown' && event.key !== 'Escape') return
  if (event.type !== 'pointerdown' || !event.target.closest?.('.nas-folder-popover')) menu.value = false
}
onMounted(() => {
  document.addEventListener('pointerdown', dismissMenu)
  document.addEventListener('scroll', dismissMenu, true)
  window.addEventListener('resize', dismissMenu)
  document.addEventListener('keydown', dismissMenu)
})
onBeforeUnmount(() => {
  reset()
  document.removeEventListener('pointerdown', dismissMenu)
  document.removeEventListener('scroll', dismissMenu, true)
  window.removeEventListener('resize', dismissMenu)
  document.removeEventListener('keydown', dismissMenu)
})
function open(row, _column, event) {
  if (!props.canQuery || (row.rowKind && row.rowKind !== 'item')) return
  event.preventDefault()
  reset()
  const x = event.clientX
  const y = event.clientY
  anchor.value = { getBoundingClientRect: () => ({ x, y, top: y, bottom: y, left: x, right: x, width: 0, height: 0 }) }
  target.value = { projectId: Number(props.projectId), taskId: Number(row.taskId || row.task?.taskId), versionId: Number(row.latestVersion?.versionId) }
  menu.value = true
}
async function loadFolders(autoLaunch = true) {
  menu.value = false
  visible.value = !autoLaunch
  error.value = ''
  attempted.value = false
  folders.value = []
  selected.value = ''
  const current = target.value
  const ids = current?.kind === 'project' ? [current.projectId] : [current?.projectId, current?.taskId, current?.versionId]
  if (!current || !ids.every(id => Number.isSafeInteger(id) && id > 0)) {
    visible.value = true
    error.value = '当前任务尚无已发布版本文件，暂时无法打开 NAS 目录'
    return
  }
  const ticket = ++generation
  controller = new AbortController()
  loading.value = true
  try {
    const response = current.kind === 'project'
      ? await getProjectStorage(current.projectId, { signal: controller.signal })
      : await getVersionDetail(current.versionId, { signal: controller.signal })
    if (ticket !== generation) return
    if (current.kind === 'project') {
      if (Number(response.data.projectId) !== current.projectId || response.data.storageStatus !== 'ready') throw new Error('项目目录尚未就绪，请刷新后重试')
      folders.value = [validateNasFolder(response.data.projectPathSnapshot)]
      files.value = []
    } else {
      // 文件入口只打开指定文件的目录，不默认为本版本其他文件。
      files.value = (response.data.files || []).filter(file => !current.fileId || file.fileId === current.fileId)
      folders.value = versionNasFolders({ ...response.data, files: files.value }, current)
    }
    selected.value = folders.value[0] || ''
    if (!selected.value) {
      error.value = '该版本暂无可用的 NAS 文件路径'
      visible.value = true
    } else if (autoLaunch && folders.value.length === 1) await launch()
    else visible.value = true
  } catch (cause) {
    if (ticket === generation) { error.value = cause.message || '读取目录失败，请关闭后重试'; visible.value = true }
  } finally {
    if (ticket === generation) loading.value = false
  }
}
async function launch() {
  if (!props.canQuery || !folders.value.includes(selected.value)) return
  const current = target.value
  const ticket = generation
  const folder = selected.value
  const file = files.value.find(item => item.nasPath?.slice(0, item.nasPath.lastIndexOf('\\')) === folder && !['thumbnail', 'proxy_media'].includes(item.role))
  if (!file && current.kind !== 'project') return
  loading.value = true
  error.value = ''
  try {
    const response = current.kind === 'project'
      ? await getProjectNasOpenTicket(current.projectId, { signal: controller?.signal })
      : await getNasOpenTicket(current.versionId, { projectId: current.projectId, taskId: current.taskId, fileId: file.fileId }, { signal: controller?.signal })
    if (ticket !== generation) return
    const { uri, folder: signedFolder } = response.data
    if (signedFolder !== folder || !/^shotgrid-nas:\/\/open-v1\/[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(uri) || uri.length > 14000) throw new Error('打开凭证不符合安全规则')
    window.location.href = uri
    attempted.value = true
  } catch (cause) {
    if (ticket === generation) { error.value = cause.message || '获取打开凭证失败'; visible.value = true }
  } finally {
    if (ticket === generation) loading.value = false
  }
}
async function downloadInstaller() {
  if (installing.value) return
  installing.value = true
  try {
    const result = await getNasOpenerPublicKey()
    const key = result.data.publicKeyXml
    if (!/^<RSAKeyValue><Modulus>[A-Za-z0-9+/=]+<\/Modulus><Exponent>[A-Za-z0-9+/=]+<\/Exponent><\/RSAKeyValue>$/.test(key)) throw new Error('服务器公钥格式无效')
    const response = await fetch(installer)
    if (!response.ok) throw new Error('安装工具下载失败')
    const template = await response.text()
    if (!template.includes('__SHOTGRID_NAS_PUBLIC_KEY__')) throw new Error('安装工具模板无效')
    // 下载属于浏览器原生能力；公钥固定编译到工具，不从协议请求动态接受。
    const script = template.replace('"__SHOTGRID_NAS_PUBLIC_KEY__"', `"${key}"`)
    const url = URL.createObjectURL(new Blob(['\ufeff', script], { type: 'text/plain;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'Install-ShotGridNas.ps1'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) { ElMessage.error(cause.message || '安装工具下载失败') }
  finally { installing.value = false }
}
async function copy() {
  if (!folders.value.includes(selected.value)) return
  if (await copyTextToClipboard(selected.value)) ElMessage.success('目录已复制，可粘贴到文件资源管理器地址栏')
  else ElMessage.error('复制失败，请手动选择并复制目录')
}
async function openTarget(value, autoLaunch = true) {
  if (!props.canQuery || loading.value) return
  reset()
  target.value = { ...value, projectId: Number(props.projectId), taskId: Number(value.taskId), versionId: Number(value.versionId) }
  await loadFolders(autoLaunch)
}
defineExpose({ open, openTarget })
</script>

<template>
  <el-popover v-model:visible="menu" popper-class="nas-folder-popover" :virtual-ref="anchor" virtual-triggering trigger="click" placement="bottom-start" :width="264" :show-arrow="false" :popper-style="{ padding: '6px', borderRadius: '10px' }">
    <div class="nas-folder-menu">
      <el-button class="nas-folder-menu__item nas-folder-menu__item--primary" text :icon="FolderOpened" :loading="loading" @click="loadFolders(true)">在文件资源管理器中打开</el-button>
      <div class="nas-folder-menu__divider" aria-hidden="true" />
      <el-button class="nas-folder-menu__item" text :icon="QuestionFilled" :disabled="loading" @click="loadFolders(false)">安装／打开帮助</el-button>
    </div>
  </el-popover>
  <el-dialog v-model="visible" title="打开 NAS 文件夹" width="620px" @close="reset">
    <div v-loading="loading">
      <el-alert v-if="error" :title="error" type="warning" :closable="false" />
      <el-form v-if="folders.length" :model="{ folder: selected }" label-position="top">
        <el-form-item label="NAS 文件夹" prop="folder">
          <el-select v-model="selected" style="width: 100%"><el-option v-for="folder in folders" :key="folder" :label="folder" :value="folder" /></el-select>
        </el-form-item>
        <el-input :model-value="selected" readonly type="textarea" :rows="3" aria-label="NAS 完整目录" />
      </el-form>
      <p>首次使用：下载下方安装脚本，在 Windows PowerShell 中运行一次（当前用户，无需管理员权限）。已安装的用户直接点击“打开文件夹”。</p>
      <p>安装命令：<code>powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-ShotGridNas.ps1</code></p>
      <el-button :loading="installing" @click="downloadInstaller">下载 Windows 安装工具</el-button>
      <p>浏览器无法可靠检测是否安装。若内置浏览器没有响应，请改用 Windows Chrome 打开本页面；仍无响应时安装后重试，或复制目录到文件资源管理器地址栏。NAS 访问使用你自己的 Windows 账号权限。</p>
      <el-alert v-if="attempted" title="已发起打开请求，若未打开，请安装或更新工具后重试，或复制目录。网页无法确认是否打开成功。" type="info" :closable="false" />
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button :disabled="!selected || loading" @click="copy">复制目录</el-button>
      <el-button type="primary" :disabled="!selected || loading" @click="launch">打开文件夹</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.nas-folder-menu { display: flex; flex-direction: column; gap: 2px; }
.nas-folder-menu__item.el-button { width: 100%; height: 40px; margin: 0; padding: 0 12px; justify-content: flex-start; border-radius: 6px; font-size: 13px; font-weight: 400; color: var(--el-text-color-regular); }
.nas-folder-menu__item :deep(.el-icon) { margin-right: 9px; font-size: 17px; color: var(--el-text-color-secondary); }
.nas-folder-menu__item--primary.el-button { color: var(--el-text-color-primary); font-weight: 500; }
.nas-folder-menu__item--primary :deep(.el-icon) { color: var(--el-color-primary); }
.nas-folder-menu__item.el-button:not(.is-disabled):hover,
.nas-folder-menu__item.el-button:not(.is-disabled):focus-visible { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.nas-folder-menu__item.el-button:focus-visible { outline: 2px solid var(--el-color-primary-light-5); outline-offset: -2px; }
.nas-folder-menu__divider { height: 1px; margin: 3px 10px; background: var(--el-border-color-lighter); }
</style>
