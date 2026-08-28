<template>
  <div v-loading="loading" class="app-container" element-loading-text="正在加载服务监控数据，请稍候！">
    <el-alert v-if="loadError" title="服务监控数据加载失败" type="error" :closable="false" show-icon class="monitor-error">
      <template #default>
        请检查网络连接后重试。
        <el-button link type="primary" :loading="loading" @click="getList">重试</el-button>
      </template>
    </el-alert>
    <el-row :gutter="10">
      <el-col :xs="24" :md="12" class="card-box">
        <el-card>
          <template #header><Cpu class="monitor-icon" /> <span>CPU</span></template>
          <el-descriptions v-if="server.cpu" :column="1" border>
            <el-descriptions-item :span="1" :rowspan="1" label="核心数">{{ formatValue(server.cpu.cpuNum) }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="用户使用率">{{ formatValue(server.cpu.used, '%') }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="系统使用率">{{ formatValue(server.cpu.sys, '%') }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="当前空闲率">{{ formatValue(server.cpu.free, '%') }}</el-descriptions-item>
          </el-descriptions>
          <el-empty v-else-if="!loading && !loadError" description="暂无 CPU 数据" :image-size="60" />
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12" class="card-box">
        <el-card>
          <template #header><Tickets class="monitor-icon" /> <span>内存</span></template>
          <el-table :data="memoryRows" row-key="key" empty-text="暂无内存数据">
            <el-table-column prop="label" label="属性" min-width="100" />
            <el-table-column prop="memory" label="内存" min-width="100">
              <template #default="{ row }">
                <span :class="{ 'text-danger': row.memoryWarning }">{{ row.memory }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="python" label="Python" min-width="100">
              <template #default="{ row }">
                <span :class="{ 'text-danger': row.pythonWarning }">{{ row.python }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="24" class="card-box">
        <el-card>
          <template #header><Monitor class="monitor-icon" /> <span>服务器信息</span></template>
          <el-descriptions v-if="server.sys" :column="2" border class="monitor-descriptions">
            <el-descriptions-item :span="1" :rowspan="1" label="服务器名称">{{ formatValue(server.sys.computerName) }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="操作系统">{{ formatValue(server.sys.osName) }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="服务器IP">{{ formatValue(server.sys.computerIp) }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="系统架构">{{ formatValue(server.sys.osArch) }}</el-descriptions-item>
          </el-descriptions>
          <el-empty v-else-if="!loading && !loadError" description="暂无服务器信息" :image-size="60" />
        </el-card>
      </el-col>

      <el-col :span="24" class="card-box">
        <el-card>
          <template #header><CoffeeCup class="monitor-icon" /> <span>Python解释器信息</span></template>
          <el-descriptions v-if="server.py" :column="2" border class="monitor-descriptions">
            <el-descriptions-item :span="1" :rowspan="1" label="Python名称">{{ formatValue(server.py.name) }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="Python版本">{{ formatValue(server.py.version) }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="启动时间">{{ formatValue(server.py.startTime) }}</el-descriptions-item>
            <el-descriptions-item :span="1" :rowspan="1" label="运行时长">{{ formatValue(server.py.runTime) }}</el-descriptions-item>
            <el-descriptions-item :span="2" :rowspan="1" label="安装路径"><span class="monitor-path">{{ formatValue(server.py.home) }}</span></el-descriptions-item>
            <el-descriptions-item :span="2" :rowspan="1" label="项目路径"><span class="monitor-path">{{ formatValue(server.sys?.userDir) }}</span></el-descriptions-item>
          </el-descriptions>
          <el-empty v-else-if="!loading && !loadError" description="暂无 Python 信息" :image-size="60" />
        </el-card>
      </el-col>

      <el-col :span="24" class="card-box">
        <el-card>
          <template #header><MessageBox class="monitor-icon" /> <span>磁盘状态</span></template>
          <el-table :data="diskRows" row-key="dirName" empty-text="暂无磁盘数据">
            <el-table-column prop="dirName" label="盘符路径" min-width="160" show-overflow-tooltip />
            <el-table-column prop="sysTypeName" label="文件系统" min-width="110" show-overflow-tooltip />
            <el-table-column prop="typeName" label="盘符名称" min-width="130" show-overflow-tooltip />
            <el-table-column prop="total" label="总大小" min-width="100" />
            <el-table-column prop="free" label="可用大小" min-width="100" />
            <el-table-column prop="used" label="已用大小" min-width="100" />
            <el-table-column prop="usage" label="已用百分比" min-width="120">
              <template #default="{ row }">
                <span :class="{ 'text-danger': row.usage > 80 }">{{ formatValue(row.usage, '%') }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { getServer } from '@/api/monitor/server'

const server = ref({})
const loading = ref(false)
const loadError = ref(false)
let active = true

const memoryRows = computed(() => {
  if (!server.value.mem && !server.value.py) return []
  return [
    { key: 'total', label: '总内存' },
    { key: 'used', label: '已用内存' },
    { key: 'free', label: '剩余内存' },
    { key: 'usage', label: '使用率' }
  ].map(row => ({
    ...row,
    memory: formatValue(server.value.mem?.[row.key], row.key === 'usage' ? '%' : ''),
    python: formatValue(server.value.py?.[row.key], row.key === 'usage' ? '%' : ''),
    memoryWarning: row.key === 'usage' && server.value.mem?.usage > 80,
    pythonWarning: row.key === 'usage' && server.value.py?.usage > 80
  }))
})
const diskRows = computed(() => server.value.sysFiles ?? [])

function formatValue(value, suffix = '') {
  return value === undefined || value === null || value === '' ? '--' : `${value}${suffix}`
}

async function getList() {
  if (loading.value) return
  loading.value = true
  loadError.value = false
  try {
    const response = await getServer()
    if (active) server.value = response.data ?? {}
  } catch {
    if (active) loadError.value = true
  } finally {
    if (active) loading.value = false
  }
}

onBeforeUnmount(() => { active = false })
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
.monitor-descriptions :deep(.el-descriptions__table) {
  table-layout: fixed;
}
.monitor-path,
.monitor-descriptions :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
</style>
