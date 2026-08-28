<template>
  <div v-loading="loading" class="app-container" element-loading-text="正在加载缓存监控数据，请稍候！">
    <el-alert v-if="loadError" title="缓存监控数据加载失败" type="error" :closable="false" show-icon class="monitor-error">
      <template #default>
        请检查网络连接后重试。
        <el-button link type="primary" :loading="loading" @click="getList">重试</el-button>
      </template>
    </el-alert>
    <el-row :gutter="10">
      <el-col :span="24" class="card-box">
        <el-card>
          <template #header><Monitor class="monitor-icon" /> <span>基本信息</span></template>
          <el-descriptions v-if="cache.info" :column="3" direction="vertical" border class="cache-descriptions">
            <el-descriptions-item v-for="item in cacheDescriptions" :key="item.key" :label="item.label" :span="1" :rowspan="1">
              {{ item.value }}
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else-if="!loading && !loadError" description="暂无缓存信息" :image-size="60" />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12" class="card-box">
        <el-card>
          <template #header><PieChart class="monitor-icon" /> <span>命令统计</span></template>
          <div v-show="commandStats.length" ref="commandstats" class="cache-chart" />
          <el-empty v-if="!commandStats.length && !loading && !loadError" description="暂无命令统计" :image-size="80" />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12" class="card-box">
        <el-card>
          <template #header><Odometer class="monitor-icon" /> <span>内存信息</span></template>
          <div v-show="cache.info" ref="usedmemory" class="cache-chart" />
          <el-empty v-if="!cache.info && !loading && !loadError" description="暂无内存信息" :image-size="80" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup name="Cache">
import { getCache } from '@/api/monitor/cache'
import * as echarts from 'echarts'

const cache = ref({})
const commandstats = ref(null)
const usedmemory = ref(null)
const loading = ref(false)
const loadError = ref(false)
const commandStats = computed(() => cache.value.commandStats ?? [])
let commandChart
let memoryChart
let active = true

const cacheDescriptions = computed(() => {
  const info = cache.value.info ?? {}
  const cpu = Number.parseFloat(info.used_cpu_user_children)
  return [
    { key: 'version', label: 'Redis版本', value: formatValue(info.redis_version) },
    { key: 'mode', label: '运行模式', value: info.redis_mode ? (info.redis_mode === 'standalone' ? '单机' : '集群') : '--' },
    { key: 'port', label: '端口', value: formatValue(info.tcp_port) },
    { key: 'clients', label: '客户端数', value: formatValue(info.connected_clients) },
    { key: 'uptime', label: '运行时间(天)', value: formatValue(info.uptime_in_days) },
    { key: 'memory', label: '使用内存', value: formatValue(info.used_memory_human) },
    { key: 'cpu', label: '使用CPU', value: Number.isFinite(cpu) ? cpu.toFixed(2) : '--' },
    { key: 'maxmemory', label: '内存配置', value: formatValue(info.maxmemory_human) },
    { key: 'aof', label: 'AOF是否开启', value: info.aof_enabled == null ? '--' : (String(info.aof_enabled) === '0' ? '否' : '是') },
    { key: 'rdb', label: 'RDB是否成功', value: formatValue(info.rdb_last_bgsave_status) },
    { key: 'keys', label: 'Key数量', value: formatValue(cache.value.dbSize) },
    { key: 'network', label: '网络入口/出口', value: `${formatValue(info.instantaneous_input_kbps, 'kps')}/${formatValue(info.instantaneous_output_kbps, 'kps')}` }
  ]
})

function formatValue(value, suffix = '') {
  return value === undefined || value === null || value === '' ? '--' : `${value}${suffix}`
}

function renderCharts() {
  if (commandstats.value && commandStats.value.length) {
    commandChart ??= echarts.init(commandstats.value, 'macarons')
    commandChart.setOption({
      tooltip: { trigger: 'item', formatter: '{a} <br/>{b} : {c} ({d}%)' },
      series: [{
        name: '命令', type: 'pie', roseType: 'radius', radius: [15, 95], center: ['50%', '38%'],
        data: commandStats.value, animationEasing: 'cubicInOut', animationDuration: 1000
      }]
    })
  }
  if (usedmemory.value && cache.value.info) {
    const memory = cache.value.info.used_memory_human
    memoryChart ??= echarts.init(usedmemory.value, 'macarons')
    memoryChart.setOption({
      tooltip: { formatter: '{b} <br/>{a} : ' + formatValue(memory) },
      series: [{
        name: '峰值', type: 'gauge', min: 0, max: 1000,
        detail: { formatter: formatValue(memory) },
        data: [{ value: Number.parseFloat(memory) || 0, name: '内存消耗' }]
      }]
    })
  }
}

function resizeCharts() {
  commandChart?.resize()
  memoryChart?.resize()
}

async function getList() {
  if (loading.value) return
  loading.value = true
  loadError.value = false
  try {
    const response = await getCache()
    if (!active) return
    cache.value = response.data ?? {}
    await nextTick()
    if (active) renderCharts()
  } catch {
    if (active) loadError.value = true
  } finally {
    if (active) loading.value = false
  }
}

onMounted(() => window.addEventListener('resize', resizeCharts))
onBeforeUnmount(() => {
  active = false
  window.removeEventListener('resize', resizeCharts)
  commandChart?.dispose()
  memoryChart?.dispose()
})
getList()
</script>

<style scoped>
.monitor-error {
  margin-bottom: 16px;
}
.monitor-icon {
  width: 1em;
  height: 1em;
  vertical-align: middle;
}
.cache-chart {
  height: 420px;
}
.cache-descriptions :deep(.el-descriptions__table) {
  table-layout: fixed;
}
.cache-descriptions :deep(.el-descriptions__cell) {
  overflow-wrap: anywhere;
}
</style>
