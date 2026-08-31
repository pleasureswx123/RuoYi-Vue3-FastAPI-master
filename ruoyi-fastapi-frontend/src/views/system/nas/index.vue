<template>
  <div class="app-container">
    <el-alert
      class="nas-help"
      title="这里维护 Shot Grid 允许使用的 NAS 根目录。新增后必须探测通过，才会出现在 5174 创建项目的下拉框中。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-form v-show="showSearch" ref="queryRef" :model="queryParams" inline label-width="82px">
      <el-form-item label="关键字" prop="keyword">
        <el-input
          v-model="queryParams.keyword"
          placeholder="名称、编码或 UNC 路径"
          clearable
          style="width: 260px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="启用状态" prop="rootStatus">
        <el-select v-model="queryParams.rootStatus" placeholder="全部" clearable style="width: 140px">
          <el-option label="已启用" value="enabled" />
          <el-option label="已停用" value="disabled" />
        </el-select>
      </el-form-item>
      <el-form-item label="探测状态" prop="probeStatus">
        <el-select v-model="queryParams.probeStatus" placeholder="全部" clearable style="width: 150px">
          <el-option label="未探测" value="unknown" />
          <el-option label="健康" value="healthy" />
          <el-option label="不可达" value="unreachable" />
          <el-option label="不可写" value="unwritable" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Plus"
          @click="handleAdd"
          v-hasPermi="['shotgrid:storageRoot:add']"
        >新增根目录</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="rootList" row-key="storageRootId">
      <el-table-column label="名称" prop="rootName" min-width="140" />
      <el-table-column label="编码" prop="rootCode" width="130" />
      <el-table-column label="UNC 根路径" prop="uncRootPath" min-width="280" show-overflow-tooltip />
      <el-table-column label="启用状态" width="100" align="center">
        <template #default="scope">
          <el-tag :type="scope.row.rootStatus === 'enabled' ? 'success' : 'info'">
            {{ scope.row.rootStatus === 'enabled' ? '已启用' : '已停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="探测状态" width="110" align="center">
        <template #default="scope">
          <el-tag :type="probeMeta(scope.row.lastProbeStatus).type">
            {{ probeMeta(scope.row.lastProbeStatus).label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近探测" prop="lastProbeTime" width="180" align="center">
        <template #default="scope">
          <span>{{ parseTime(scope.row.lastProbeTime) || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="错误摘要" prop="lastErrorMessage" min-width="210" show-overflow-tooltip>
        <template #default="scope">{{ scope.row.lastErrorMessage || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="310" align="center" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="Connection"
            :loading="probingId === scope.row.storageRootId"
            :disabled="deletingId === scope.row.storageRootId"
            @click="handleProbe(scope.row)"
            v-hasPermi="['shotgrid:storageRoot:probe']"
          >探测</el-button>
          <el-button
            link
            type="primary"
            icon="Edit"
            :disabled="deletingId === scope.row.storageRootId"
            @click="handleUpdate(scope.row)"
            v-hasPermi="['shotgrid:storageRoot:edit']"
          >修改</el-button>
          <el-button
            link
            :type="scope.row.rootStatus === 'enabled' ? 'danger' : 'success'"
            :disabled="deletingId === scope.row.storageRootId"
            @click="handleToggle(scope.row)"
            v-hasPermi="['shotgrid:storageRoot:edit']"
          >{{ scope.row.rootStatus === 'enabled' ? '停用' : '启用' }}</el-button>
          <el-button
            v-if="scope.row.rootStatus === 'disabled'"
            link
            type="danger"
            icon="Delete"
            :loading="deletingId === scope.row.storageRootId"
            @click="handleDelete(scope.row)"
            v-hasPermi="['shotgrid:storageRoot:remove']"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <el-dialog :title="dialogTitle" v-model="open" width="650px" append-to-body>
      <el-form ref="rootRef" :model="form" :rules="rules" label-width="112px">
        <el-form-item label="根目录名称" prop="rootName">
          <el-input v-model="form.rootName" placeholder="例如：ShotGrid 主存储" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="根目录编码" prop="rootCode">
          <el-input v-model="form.rootCode" placeholder="例如：SHOTGRID_MAIN" maxlength="50" />
          <div class="form-tip">稳定标识，只能使用大写字母、数字、下划线或短横线。</div>
        </el-form-item>
        <el-form-item label="UNC 根路径" prop="uncRootPath">
          <el-input v-model="form.uncRootPath" placeholder="例如：\\192.168.10.64\web\ShotGrid" maxlength="1000" />
          <div class="form-tip">填写共享目录本身，不要填写项目子目录；保存后请点击“探测”。</div>
        </el-form-item>
        <el-form-item label="启用状态" prop="rootStatus">
          <el-radio-group v-model="form.rootStatus">
            <el-radio value="enabled">启用</el-radio>
            <el-radio value="disabled">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确定</el-button>
          <el-button @click="cancel">取消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="NasRoot">
import {
  addStorageRoot,
  deleteStorageRoot,
  getStorageRoot,
  listStorageRoots,
  probeStorageRoot,
  updateStorageRoot
} from '@/api/shot-grid/storageRoot'

const { proxy } = getCurrentInstance()

const loading = ref(false)
const probingId = ref(null)
const deletingId = ref(null)
const showSearch = ref(true)
const rootList = ref([])
const total = ref(0)
const open = ref(false)
const dialogTitle = ref('')

const data = reactive({
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    keyword: undefined,
    rootStatus: undefined,
    probeStatus: undefined
  },
  form: {},
  rules: {
    rootName: [{ required: true, message: '根目录名称不能为空', trigger: 'blur' }],
    rootCode: [
      { required: true, message: '根目录编码不能为空', trigger: 'blur' },
      { pattern: /^[A-Za-z0-9][A-Za-z0-9_-]{1,49}$/, message: '编码格式不正确', trigger: 'blur' }
    ],
    uncRootPath: [
      { required: true, message: 'UNC 根路径不能为空', trigger: 'blur' },
      { pattern: /^\\\\[^\\/]+\\[^\\/]+(?:\\[^\\/]+)*\\?$/, message: '请输入合法的 Windows UNC 路径', trigger: 'blur' }
    ],
    rootStatus: [{ required: true, message: '请选择启用状态', trigger: 'change' }]
  }
})

const { queryParams, form, rules } = toRefs(data)

function getList() {
  loading.value = true
  listStorageRoots(queryParams.value)
    .then(response => {
      rootList.value = response.rows || []
      total.value = response.total || 0
    })
    .finally(() => {
      loading.value = false
    })
}

function probeMeta(status) {
  return {
    healthy: { label: '健康', type: 'success' },
    unreachable: { label: '不可达', type: 'danger' },
    unwritable: { label: '不可写', type: 'warning' },
    unknown: { label: '未探测', type: 'info' }
  }[status] || { label: status || '未知', type: 'info' }
}

function reset() {
  form.value = {
    storageRootId: undefined,
    rootName: '',
    rootCode: '',
    uncRootPath: '',
    rootStatus: 'enabled',
    remark: undefined,
    lockVersion: undefined
  }
  proxy.resetForm('rootRef')
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function handleAdd() {
  reset()
  dialogTitle.value = '新增 NAS 根目录'
  open.value = true
}

function handleUpdate(row) {
  reset()
  getStorageRoot(row.storageRootId).then(response => {
    form.value = response.data
    dialogTitle.value = '修改 NAS 根目录'
    open.value = true
  })
}

function cancel() {
  open.value = false
  reset()
}

function submitForm() {
  proxy.$refs.rootRef.validate(valid => {
    if (!valid) return
    const payload = {
      rootName: form.value.rootName,
      rootCode: form.value.rootCode.toUpperCase(),
      uncRootPath: form.value.uncRootPath,
      rootStatus: form.value.rootStatus,
      remark: form.value.remark
    }
    const request = form.value.storageRootId
      ? updateStorageRoot(form.value.storageRootId, { ...payload, lockVersion: form.value.lockVersion })
      : addStorageRoot(payload)
    request.then(() => {
      proxy.$modal.msgSuccess(form.value.storageRootId ? '修改成功' : '新增成功，请继续点击探测')
      open.value = false
      getList()
    })
  })
}

function handleToggle(row) {
  const targetStatus = row.rootStatus === 'enabled' ? 'disabled' : 'enabled'
  const actionText = targetStatus === 'enabled' ? '启用' : '停用'
  proxy.$modal.confirm(`确认${actionText}根目录“${row.rootName}”吗？`).then(() => {
    return updateStorageRoot(row.storageRootId, {
      rootName: row.rootName,
      rootCode: row.rootCode,
      uncRootPath: row.uncRootPath,
      rootStatus: targetStatus,
      remark: row.remark,
      lockVersion: row.lockVersion
    })
  }).then(() => {
    proxy.$modal.msgSuccess(`${actionText}成功`)
    getList()
  }).catch(() => {})
}

function handleDelete(row) {
  return proxy.$modal
    .confirm(`确认删除根目录“${row.rootName}”的平台配置吗？此操作不会删除 NAS 中的目录或文件。`)
    .then(() => {
      deletingId.value = row.storageRootId
      return deleteStorageRoot(row.storageRootId, { lockVersion: row.lockVersion })
    })
    .then(() => {
      proxy.$modal.msgSuccess('删除成功')
      getList()
    })
    .catch(() => {})
    .finally(() => {
      deletingId.value = null
    })
}

function handleProbe(row) {
  probingId.value = row.storageRootId
  probeStorageRoot(row.storageRootId)
    .then(response => {
      const result = response.data
      if (result.lastProbeStatus === 'healthy') {
        proxy.$modal.msgSuccess('读写探测通过，创建项目时已可选择')
      } else {
        proxy.$modal.msgWarning(result.lastErrorMessage || '探测未通过')
      }
      getList()
    })
    .finally(() => {
      probingId.value = null
    })
}

getList()
</script>

<style scoped>
.nas-help {
  margin-bottom: 18px;
}

.form-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 20px;
}
</style>
