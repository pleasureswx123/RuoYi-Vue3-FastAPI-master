<script setup>
import { BellFilled } from '@element-plus/icons-vue'
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/store/modules/session'
import { useFeedbackInbox } from '@/store/modules/feedbackInbox'

const session = useSessionStore()
const inbox = useFeedbackInbox()
const router = useRouter()
watch(() => session.permissions.some(p => ['*:*:*', 'shotgrid:note:list'].includes(p)) && Number(session.user?.userId), (id, _, cleanup) => {
  if (id) cleanup(inbox.listen(id))
}, { immediate: true })

function openInbox() {
  router.push({ path: '/workbench', query: { projectId: session.activeProjectId || undefined, tab: 'messages', message: String(inbox.latestId) } })
}
</script>

<template>
  <Teleport to="body">
    <aside v-if="inbox.count" class="feedback-notification" aria-label="新反馈提醒" role="status">
      <el-card class="feedback-card" shadow="always">
        <div class="feedback-heading">
          <el-icon class="feedback-bell" aria-hidden="true"><BellFilled /></el-icon>
          <div>
            <strong>收到制作反馈</strong>
            <p>你有 <b>{{ inbox.count }}</b> 条未读消息</p>
          </div>
        </div>
        <el-button type="primary" @click="openInbox">查看我的消息</el-button>
      </el-card>
    </aside>
  </Teleport>
</template>

<style scoped>
.feedback-notification {
  --notice-bg: #20252d;
  --notice-text: #fff;
  --notice-secondary: #e2e6ed;
  --notice-accent: #ffc063;
  --notice-button-text: #271a09;
  position: fixed;
  z-index: var(--el-index-popper, 2000);
  right: 20px;
  bottom: 20px;
  width: min(320px, calc(100vw - 40px));
}
:root.dark .feedback-notification {
  --notice-bg: #fffaf1;
  --notice-text: #20252d;
  --notice-secondary: #49515c;
  --notice-accent: #934000;
  --notice-button-text: #fff;
}
.feedback-notification .feedback-card {
  --el-card-bg-color: var(--notice-bg);
  --el-card-text-color: var(--notice-text);
  --el-card-border-color: var(--notice-accent);
  --el-card-border-radius: 12px;
  background-color: var(--notice-bg);
  color: var(--notice-text);
  border-inline-start: 5px solid var(--notice-accent);
  box-shadow: 0 8px 30px rgb(0 0 0 / 32%);
}
.feedback-heading { display: flex; gap: 14px; align-items: center; color: var(--notice-text); }
.feedback-heading strong { font-size: 20px; line-height: 1.35; }
.feedback-heading p { margin: 4px 0 0; font-size: 16px; color: var(--notice-secondary); }
.feedback-heading b { color: var(--notice-accent); font-size: 20px; }
.feedback-bell { color: var(--notice-accent); font-size: 32px; }
.feedback-card .el-button {
  --el-button-bg-color: var(--notice-accent);
  --el-button-border-color: var(--notice-accent);
  --el-button-text-color: var(--notice-button-text);
  --el-button-hover-bg-color: var(--notice-text);
  --el-button-hover-border-color: var(--notice-text);
  --el-button-hover-text-color: var(--notice-bg);
  margin-top: 16px;
  width: 100%;
  min-height: 36px;
}
</style>
