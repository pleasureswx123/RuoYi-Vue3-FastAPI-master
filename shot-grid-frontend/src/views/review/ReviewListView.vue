<script setup>
import { Tickets } from '@element-plus/icons-vue'
import BusinessBoundaryView from '@/views/_shared/BusinessBoundaryView.vue'
</script>

<template>
  <BusinessBoundaryView
    eyebrow="REVIEWS"
    title="版本审核"
    description="审核单、不可覆盖版本、意见与审核动作在同一条生产链路中保持可追溯。"
    :icon="Tickets"
    boundary-text="待审核版本、媒体查看、意见回复和通过/退回/稍后决定动作将在下一批接入现有真实审核 API；当前页面不展示虚构待办。"
  />
</template>
