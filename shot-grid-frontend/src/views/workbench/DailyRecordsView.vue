<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButtonGroup, ElMessage, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/button-group/style/css'
import { dailyRequest, saveDailyRecords } from '@/api/shot-grid/dailyRecords'
import { getMineTaskPage, getTaskDetail } from '@/api/shot-grid/tasks'
import { useSessionStore } from '@/store/modules/session'
import { useLeaveProtection } from '@/composables/useLeaveProtection'
import { createIdempotencyState } from '@/utils/idempotency'

const route = useRoute(), router = useRouter(), session = useSessionStore()
const statistics = computed(() => route.name === 'production-statistics')
const projectId = computed(() => Number(route.query.projectId || session.activeProjectId || 0))
const localDate = value => { const d = new Date(value); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
const today = () => localDate(new Date())
const filters = reactive({ dates: [today(), today()], platform: '', userId: null })
const filterRef = ref(), formRef = ref(), loading = ref(false), saving = ref(false), exporting = ref(false), error = ref('')
const rows = ref([]), total = ref(0), page = ref(1), summary = ref({ groups: [], submittedVersions: 0, approvedTasks: 0 })
const editor = ref(false), tasks = ref([]), taskPage = ref(0), moreTasks = ref(false), taskLoading = ref(false), historyRow = ref(null)
const form = reactive({ taskId: null, recordDate: today(), lines: [] })
const rememberedKey = () => `daily-platform:${session.user?.userId}:${projectId.value}`
const lastChoice = () => { try { return JSON.parse(sessionStorage.getItem(rememberedKey()) || '{}') } catch { return {} } }
const original = ref(''), baseline = () => JSON.stringify(form)
const dirty = computed(() => editor.value && baseline() !== original.value)
let controller, taskController
const canLeave = async () => {
  if (saving.value || exporting.value) return false
  if (!dirty.value) return true
  return ElMessageBox.confirm('还有未保存的记录，确定离开？', '保留记录', { type: 'warning' }).then(() => true).catch(() => false)
}
useLeaveProtection(canLeave, () => dirty.value || saving.value)
const rules = { taskId: [{ required: true, message: '请选择本人任务', trigger: 'change' }], recordDate: [{ required: true, message: '请选择日期', trigger: 'change' }] }
const filterRules = { dates: [{ validator: (_rule, value, done) => done(value?.length === 2 && value[0] <= value[1] && (new Date(value[1]) - new Date(value[0])) / 86400000 < 366 ? undefined : new Error('请选择不超过 366 天的日期范围')), trigger: 'change' }] }
const pointsRule = { validator: (_rule, _value, done) => done(form.lines.some(l => !l.removed && (l.actualPoints === null || l.actualPoints === undefined) && (l.unitPoints === null || l.unitPoints === undefined)) ? new Error('填写实际积分或单次估算积分，免费填 0') : undefined), trigger: 'change' }
const activeLines = computed(() => form.lines.filter(l => !l.removed))
const platformOptions = computed(() => [...new Set([...rows.value.map(r => r.platform), ...summary.value.groups.map(r => r.platform)])])
const platformChoices = computed(() => [...new Set(['即梦', '可灵', '海螺', 'runway', ...platformOptions.value])])
const people = computed(() => summary.value.people || [...new Map(summary.value.groups.map(r => [r.userId, r])).values()])
function params(pageNum = page.value) { return { start: filters.dates[0], end: filters.dates[1], platform: filters.platform || undefined, userId: filters.userId || undefined, pageNum, pageSize: 50 } }
async function load() {
  controller?.abort()
  rows.value = []; total.value = 0; summary.value = { groups: [], submittedVersions: 0, approvedTasks: 0 }; error.value = ''
  if (!projectId.value) return
  const request = new AbortController(); controller = request; loading.value = true
  try {
    const options = { signal: request.signal, statistics: statistics.value }
    const [details, stats] = await Promise.all([dailyRequest(projectId.value, statistics.value ? '/details' : '', params(), options), statistics.value ? dailyRequest(projectId.value, '', params(), options) : Promise.resolve(null)])
    if (request.signal.aborted) return
    rows.value = details.data.rows; total.value = details.data.total
    if (stats) summary.value = stats.data
  } catch (e) { if (!request.signal.aborted) error.value = e.message || '读取失败，请重试' }
  finally { if (controller === request) loading.value = false }
}
async function search() { if (await filterRef.value.validate().catch(() => false)) { page.value = 1; await load() } }
function range(kind) {
  const start = new Date(), end = new Date(); start.setHours(0, 0, 0, 0)
  if (kind === 'week' || kind === 'last-week') { start.setDate(start.getDate() - (start.getDay() + 6) % 7); if (kind === 'last-week') { end.setTime(start.getTime() - 86400000); start.setDate(start.getDate() - 7) } }
  if (kind === 'month' || kind === 'last-month') { start.setDate(1); if (kind === 'last-month') { end.setTime(start.getTime() - 86400000); start.setMonth(start.getMonth() - 1) } }
  filters.dates = [localDate(start), localDate(end)]
  if (filterRef.value) search()
}
async function loadTasks(reset = true) {
  if (reset) { taskController?.abort(); tasks.value = []; taskPage.value = 0 }
  const request = new AbortController(); taskController = request; taskLoading.value = true
  try {
    const result = await getMineTaskPage({ projectId: projectId.value, pageNum: taskPage.value + 1, pageSize: 100 }, { signal: request.signal })
    if (request.signal.aborted) return
    tasks.value = [...new Map([...tasks.value, ...result.rows].map(t => [t.taskId, t])).values()]; taskPage.value++
    moreTasks.value = result.hasNext || tasks.value.length < result.total
  } catch (e) { if (!request.signal.aborted) ElMessage.error(e.message || '任务加载失败') }
  finally { if (taskController === request) taskLoading.value = false }
}
function newLine(source = {}) {
  const hex = createIdempotencyState('daily').forPayload({}).split(':').at(-1).replaceAll('-', '')
  const recordId = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  return { recordId, lockVersion: 0, platform: source.platform || '', account: source.account || '', model: source.model || '', mediaType: source.mediaType || 'image', generatedCount: 0, actualPoints: null, unitPoints: source.unitPoints ?? null, remark: '', removed: false }
}
async function openEditor(row) {
  if (!await canLeave()) return
  form.taskId = row?.taskId || Number(route.query.taskId) || null; form.recordDate = row?.recordDate || today()
  form.lines = row ? [{ ...row, actualPoints: row.actualPoints === null ? null : Number(row.actualPoints), unitPoints: row.unitPoints === null ? null : Number(row.unitPoints), removed: false }] : [newLine(rows.value[0] || lastChoice())]
  original.value = baseline(); editor.value = true
  await loadTasks()
  if (form.taskId && !tasks.value.some(t => t.taskId === form.taskId)) {
    try { const res = await getTaskDetail(form.taskId); if (editor.value && Number(res.data.project.projectId) === projectId.value) tasks.value.push(res.data) }
    catch { ElMessage.warning('任务不在当前可用列表中，请重新选择') }
  }
}
async function closeEditor(done) { if (await canLeave()) { editor.value = false; if (typeof done === 'function') done() } }
async function save() {
  if (saving.value || !await formRef.value.validate().catch(() => false)) return
  saving.value = true
  try {
    const lines = form.lines.map(({ recordId, lockVersion, platform, account, model, mediaType, generatedCount, actualPoints, unitPoints, remark, removed }) => ({ recordId, lockVersion, platform, account, model, mediaType, generatedCount, actualPoints: actualPoints ?? null, unitPoints: unitPoints ?? null, remark, removed: !!removed }))
    await saveDailyRecords(projectId.value, { taskId: form.taskId, recordDate: form.recordDate, lines })
    try { const last = activeLines.value.at(-1); if (last) sessionStorage.setItem(rememberedKey(), JSON.stringify({ platform: last.platform, model: last.model, account: last.account, unitPoints: last.unitPoints, mediaType: last.mediaType })) } catch { /* 偏好保存失败不影响业务提交。 */ }
    original.value = baseline(); editor.value = false; ElMessage.success('记录已保存'); await load()
  } catch (e) { ElMessage.error(e.message || '保存失败，填写内容已保留') }
  finally { saving.value = false }
}
function removeLine(row) {
  if (rows.value.some(r => r.recordId === row.recordId)) row.removed = true
  else form.lines.splice(form.lines.indexOf(row), 1)
}
async function exportData() {
  if (exporting.value || !await filterRef.value.validate().catch(() => false)) return
  exporting.value = true
  const request = new AbortController(), pid = projectId.value, stat = statistics.value, query = params(1)
  try {
    const all = []
    for (let n = 1; ; n++) {
      if (pid !== projectId.value || stat !== statistics.value) throw new Error('项目已变化，请重新导出')
      const res = await dailyRequest(pid, stat ? '/details' : '', { ...query, pageNum: n, pageSize: 100 }, { statistics: stat, signal: request.signal })
      all.push(...res.data.rows)
      if (all.length >= res.data.total) break
      if (!res.data.rows.length || n >= 100) throw new Error('记录较多，请缩小日期范围后导出')
    }
    const ExcelJS = (await import('exceljs')).default, workbook = new ExcelJS.Workbook(), sheet = workbook.addWorksheet('每日记录')
    sheet.addRow(['日期', '任务', '制作人', '平台', '账号', '模型', '类型', '生成量', '实际积分', '单次估算积分', '统计积分', '口径', '备注'])
    all.forEach(r => sheet.addRow([r.recordDate, r.taskName, r.userName, r.platform, r.account, r.model, r.mediaType === 'image' ? '图片（张）' : '视频（条）', r.generatedCount, r.actualPoints, r.unitPoints, r.statisticalPoints, r.estimated ? '估算' : '实际', r.remark]))
    sheet.columns.forEach(c => { c.width = 20 }); sheet.getRow(1).font = { bold: true }
    if (stat) { const s = workbook.addWorksheet('按平台汇总'); s.addRow(['平台', '制作人', '类型', '生成量', '积分', '估算记录数']); const res = await dailyRequest(pid, '', query, { statistics: true }); res.data.groups.forEach(g => s.addRow([g.platform, g.userName, g.mediaType, g.generatedCount, g.points, g.estimatedRecords])); s.addRow([]); s.addRow(['提交轮次（不按平台归因）', res.data.submittedVersions]); s.addRow(['期间曾通过任务（去重）', res.data.approvedTasks]) }
    const blob = new Blob([await workbook.xlsx.writeBuffer()]), url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = `制作记录-${query.start}-${query.end}.xlsx`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) { ElMessage.error(e.message || '导出失败') }
  finally { exporting.value = false }
}
watch(() => [projectId.value, statistics.value, session.permissions.join('|')], () => { editor.value = false; original.value = ''; page.value = 1; filters.platform = ''; filters.userId = null; if (statistics.value) { range('week'); if (!filterRef.value) load() } else { filters.dates = [today(), today()]; load() } }, { immediate: true })
onBeforeUnmount(() => { controller?.abort(); taskController?.abort() })
</script>

<template>
  <section class="sg-page daily-page">
    <header class="daily-heading"><div><h2>{{ statistics ? '产出统计' : '每日记录' }}</h2><p>{{ statistics ? '按平台统计消耗，按任务统计产出' : '选任务，记录各平台生成量与积分，保存即可。' }}</p></div><el-button v-if="!statistics" type="primary" :disabled="!projectId" @click="openEditor()">记录今日产出</el-button></header>
    <el-empty v-if="!projectId" description="请先选择项目"><el-button @click="router.push('/projects')">选择项目</el-button></el-empty>
    <template v-else>
      <el-form ref="filterRef" :model="filters" :rules="filterRules" inline class="daily-filters">
        <el-form-item label="日期" prop="dates"><el-date-picker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" /></el-form-item>
        <el-form-item><el-button-group><el-button @click="range('today')">今天</el-button><el-button @click="range('week')">本周</el-button><el-button @click="range('last-week')">上周</el-button><el-button @click="range('month')">本月</el-button><el-button @click="range('last-month')">上月</el-button></el-button-group></el-form-item>
        <el-form-item label="平台" prop="platform"><el-select v-model="filters.platform" filterable allow-create default-first-option clearable placeholder="全部平台" style="width:150px"><el-option v-for="p in platformOptions" :key="p" :value="p" :label="p" /></el-select></el-form-item>
        <el-form-item v-if="statistics" label="制作人" prop="userId"><el-select v-model="filters.userId" clearable placeholder="全部制作人" style="width:150px"><el-option v-for="p in people" :key="p.userId" :value="p.userId" :label="p.userName" /></el-select></el-form-item>
        <el-form-item><el-button type="primary" :loading="loading" @click="search">查询</el-button><el-button :loading="exporting" :disabled="loading || !!error" @click="exportData">导出 Excel</el-button></el-form-item>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false"><el-button link @click="search">重试</el-button></el-alert>
      <template v-if="statistics">
        <el-descriptions :column="2" border><el-descriptions-item label="期间提交轮次">{{ summary.submittedVersions }}</el-descriptions-item><el-descriptions-item label="期间曾通过任务（去重）">{{ summary.approvedTasks }}</el-descriptions-item></el-descriptions>
        <p class="daily-hint">提交与通过数量不按平台归因，也不随平台筛选变化。不同平台积分不相加；生成量不是通过量。</p>
        <el-table v-loading="loading" :data="summary.platforms || []" row-key="platform" border empty-text="暂无平台消耗"><el-table-column prop="platform" label="平台汇总" /><el-table-column prop="points" label="该平台积分" /><el-table-column prop="images" label="生成图片（张）" /><el-table-column prop="videos" label="生成视频（条）" /><el-table-column prop="estimatedRecords" label="估算记录数" /></el-table><h3>人员明细</h3>
        <el-table v-loading="loading" :data="summary.groups" :row-key="r => `${r.platform}:${r.userId}:${r.mediaType}`" empty-text="该范围暂无消耗记录" border>
          <el-table-column prop="platform" label="平台" /><el-table-column prop="userName" label="制作人" /><el-table-column label="类型"><template #default="{ row }">{{ row.mediaType === 'image' ? '图片（张）' : '视频（条）' }}</template></el-table-column><el-table-column prop="generatedCount" label="生成量" /><el-table-column prop="points" label="统计积分" /><el-table-column prop="estimatedRecords" label="其中估算记录数" />
        </el-table><h3>记录明细</h3>
      </template>
      <el-table v-loading="loading" :data="rows" row-key="recordId" border empty-text="暂无记录，填写后将在这里显示">
        <el-table-column prop="recordDate" label="日期" width="110" /><el-table-column prop="taskName" label="任务" min-width="180" show-overflow-tooltip /><el-table-column v-if="statistics" prop="userName" label="制作人" width="100" /><el-table-column prop="platform" label="平台" width="110" /><el-table-column prop="account" label="账号" width="100" /><el-table-column prop="model" label="模型" width="110" /><el-table-column label="生成量" width="100"><template #default="{ row }">{{ row.generatedCount }} {{ row.mediaType === 'image' ? '张' : '条' }}</template></el-table-column><el-table-column label="统计积分" width="145"><template #default="{ row }">{{ row.statisticalPoints }} <el-tag size="small" :type="row.estimated ? 'warning' : 'success'">{{ row.estimated ? '估算' : '实际' }}</el-tag></template></el-table-column><el-table-column prop="remark" label="说明" min-width="130" show-overflow-tooltip /><el-table-column label="记录" width="120"><template #default="{ row }"><el-button v-if="!statistics" link type="primary" @click="openEditor(row)">修改</el-button><el-button v-if="row.history?.length" link @click="historyRow = row">历史</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :page-size="50" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </template>
    <el-drawer v-model="editor" title="记录每日产出与积分" size="min(1200px, 96vw)" :before-close="closeEditor" destroy-on-close :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="saving">
        <div class="daily-context"><el-form-item label="日期" prop="recordDate"><el-date-picker v-model="form.recordDate" value-format="YYYY-MM-DD" :disabled="rows.some(r => r.recordId === form.lines[0]?.recordId)" :disabled-date="d => localDate(d) > today()" /></el-form-item><el-form-item label="本人任务" prop="taskId"><el-select v-model="form.taskId" filterable placeholder="选择镜头或资产任务" :loading="taskLoading" :disabled="rows.some(r => r.recordId === form.lines[0]?.recordId)"><el-option v-for="t in tasks" :key="t.taskId" :value="t.taskId" :label="t.taskName" /><template #footer><el-button v-if="moreTasks" link :loading="taskLoading" @click="loadTasks(false)">加载更多任务</el-button></template></el-select></el-form-item></div>
        <p class="daily-hint">制作人自动记录为当前账号。同一天、同任务、同平台／账号／模型／类型请填写累计量。实际扣点未知时填单次估算积分；免费填 0。</p>
        <el-table :data="activeLines" row-key="recordId" border>
          <el-table-column label="平台" min-width="140"><template #default="{ row }"><el-form-item :prop="`lines.${form.lines.indexOf(row)}.platform`" :rules="[{ required: true, whitespace: true, message: '填写平台', trigger: 'blur' }]"><el-select v-model="row.platform" filterable allow-create default-first-option placeholder="选择或输入" aria-label="平台"><el-option v-for="p in platformChoices" :key="p" :value="p" :label="p" /></el-select></el-form-item></template></el-table-column>
          <el-table-column label="账号（选填）" min-width="120"><template #default="{ row }"><el-form-item :prop="`lines.${form.lines.indexOf(row)}.account`"><el-input v-model="row.account" maxlength="80" placeholder="账号标识，不填密码" aria-label="平台账号" /></el-form-item></template></el-table-column>
          <el-table-column label="模型（选填）" min-width="120"><template #default="{ row }"><el-form-item :prop="`lines.${form.lines.indexOf(row)}.model`"><el-input v-model="row.model" maxlength="80" aria-label="模型" /></el-form-item></template></el-table-column>
          <el-table-column label="类型" width="110"><template #default="{ row }"><el-form-item :prop="`lines.${form.lines.indexOf(row)}.mediaType`"><el-select v-model="row.mediaType" aria-label="类型"><el-option label="图片" value="image" /><el-option label="视频" value="video" /></el-select></el-form-item></template></el-table-column>
          <el-table-column label="生成量" width="115"><template #default="{ row }"><el-form-item :prop="`lines.${form.lines.indexOf(row)}.generatedCount`" :rules="[{ required: true, type: 'number', message: '填写数量' }]"><el-input-number v-model="row.generatedCount" :min="0" :max="1000000" :precision="0" :controls="false" aria-label="生成量" /></el-form-item></template></el-table-column>
          <el-table-column label="实际消耗积分" width="130"><template #default="{ row }"><el-form-item :prop="`lines.${form.lines.indexOf(row)}.actualPoints`"><el-input-number v-model="row.actualPoints" :min="0" :max="999999999" :precision="4" :controls="false" placeholder="未知留空" aria-label="实际积分" /></el-form-item></template></el-table-column>
          <el-table-column label="单次估算积分" width="130"><template #default="{ row }"><el-form-item :prop="`lines.${form.lines.indexOf(row)}.unitPoints`"><el-input-number v-model="row.unitPoints" :min="0" :max="999999" :precision="4" :controls="false" placeholder="实际未知时填" aria-label="单次估算积分" /></el-form-item></template></el-table-column>
          <el-table-column label="移除" width="70"><template #default="{ row }"><el-button link type="danger" @click="removeLine(row)">移除</el-button></template></el-table-column>
        </el-table>
        <el-form-item prop="lines" :rules="[pointsRule, { validator: (_r, v, done) => done(v.length ? undefined : new Error('至少添加一条记录')), trigger: 'change' }]" />
        <el-button :disabled="form.lines.length >= 30" @click="form.lines.push(newLine(activeLines.at(-1)))">＋ 添加平台记录</el-button>
        <el-form-item v-for="(line, index) in activeLines" :key="line.recordId" :label="`${line.platform || `第 ${index + 1} 行`} · 说明（选填）`" :prop="`lines.${form.lines.indexOf(line)}.remark`"><el-input v-model="line.remark" maxlength="500" placeholder="异常消耗或其他补充，无需重复写日报" /></el-form-item>
      </el-form>
      <template #footer><el-button :disabled="saving" @click="closeEditor()">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存记录</el-button></template>
    </el-drawer>
    <el-dialog :model-value="!!historyRow" title="记录修改历史" width="min(800px, 94vw)" @close="historyRow = null"><el-table :data="historyRow?.history || []" row-key="at"><el-table-column prop="at" label="修改时间" /><el-table-column prop="by" label="操作人 ID" /><el-table-column prop="before.generatedCount" label="修改前生成量" /><el-table-column prop="before.statisticalPoints" label="修改前积分" /><el-table-column prop="before.platform" label="修改前平台" /></el-table></el-dialog>
  </section>
</template>

<style scoped>
.daily-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:16px; }
.daily-heading h2 { margin:0; }.daily-heading p,.daily-hint { color:var(--el-text-color-secondary); font-size:13px; }
.daily-context { display:grid; grid-template-columns:240px 1fr; gap:20px; }.daily-context .el-select { width:100%; }
.daily-page :deep(.el-table .el-input-number) { width:100%; }.daily-page :deep(.el-table .el-form-item) { margin-bottom:16px; margin-top:12px; }
.daily-page .el-pagination { margin-top:16px; }.daily-filters { margin-bottom:12px; }
@media(max-width:700px) { .daily-context { grid-template-columns:1fr; } }
</style>
