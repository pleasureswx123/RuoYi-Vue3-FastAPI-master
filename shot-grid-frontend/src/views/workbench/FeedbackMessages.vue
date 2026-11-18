<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ReviewReferenceFiles from '@/components/review/ReviewReferenceFiles.vue'
import request from '@/utils/request'
import { useFeedbackInbox } from '@/store/modules/feedbackInbox'

const inbox = useFeedbackInbox()
const route = useRoute()
const router = useRouter()
const page = ref(1)
const rows = ref([])
const total = ref(0)
const error = ref('')
const loading = ref(false)
let generation = 0
let reading = null

async function read(row) {
  if (reading || row.readAt) return
  reading = row.messageId
  try {
    await inbox.markRead(row.messageId)
    row.readAt = new Date().toISOString()
    if (Number(route.query.message) === row.messageId) {
      const query = { ...route.query }
      delete query.message
      await router.replace({ query })
    }
  } catch { error.value = '标记已读失败，请重试' }
  finally { reading = null }
}

async function load() {
  const token = ++generation
  loading.value = true
  error.value = ''
  try {
    const { data } = await request.get('/shot-grid/my-messages', { params: { page: page.value, size: 20, focus: route.query.message || undefined } })
    if (token !== generation) return
    rows.value = data.rows
    total.value = data.total
    if (data.page) page.value = data.page
    const target = rows.value.find(row => row.messageId === Number(route.query.message))
    if (target && !target.readAt) await read(target)
    else if (route.query.message) {
      const query = { ...route.query }
      delete query.message
      await router.replace({ query })
    }
  } catch { if (token === generation) error.value = '消息加载失败，请重试' }
  finally { if (token === generation) loading.value = false }
}
watch([() => route.query.message, () => inbox.revision], load, { immediate: true })
</script>

<template>
  <section aria-label="我的反馈消息">
    <el-alert v-if="error" type="error" :title="error" :closable="false"><el-button link @click="load">重试</el-button></el-alert>
    <el-table v-loading="loading" :data="rows" row-key="messageId" empty-text="暂无反馈消息">
      <el-table-column label="任务" min-width="170"><template #default="{ row }"><strong>{{ row.taskName }}</strong><div>{{ row.projectName }} · {{ row.versionNumber }}</div></template></el-table-column>
      <el-table-column label="完整反馈" min-width="260"><template #default="{ row }">
        <div v-for="(issue, index) in row.issues" :key="index" class="message-issue">
          <span v-if="row.issues.length > 1">{{ index + 1 }}. </span><span>{{ issue.content || '画面标注' }}</span>
          <div v-if="issue.comment">复核意见：{{ issue.comment }}</div>
          <small v-if="issue.candidateNo">候选 {{ String(issue.candidateNo).padStart(2, '0') }} </small>
          <small v-if="issue.mediaTimeMs != null">定位：{{ issue.mediaTimeMs / 1000 }} 秒 </small>
          <small v-if="issue.annotations?.items?.length">画面标注 {{ issue.annotations.items.length }} 处 </small>
          <ReviewReferenceFiles v-if="issue.referenceFiles?.length" :files="issue.referenceFiles" compact />
        </div>
        <router-link :to="{ path: '/tasks/' + row.taskId, query: { projectId: row.projectId, section: 'feedback' } }">查看任务反馈</router-link>
      </template></el-table-column>
      <el-table-column label="发送人 / 时间" min-width="145"><template #default="{ row }">{{ row.senderName }}<div>{{ row.createdAt.replace('T', ' ').slice(0, 19) }}</div></template></el-table-column>
      <el-table-column label="状态" width="105"><template #default="{ row }"><span v-if="row.readAt">已读</span><el-button v-else link type="primary" @click="read(row)">标为已读</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="load" />
  </section>
</template>

<style scoped>
.message-issue { white-space: pre-wrap; overflow-wrap: anywhere; margin-bottom: 6px; }
</style>
