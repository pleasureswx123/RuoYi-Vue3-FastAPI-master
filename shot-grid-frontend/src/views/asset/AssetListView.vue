<script setup>
import { Box } from '@element-plus/icons-vue'
import BusinessBoundaryView from '@/views/_shared/BusinessBoundaryView.vue'
</script>

<template>
  <BusinessBoundaryView
    eyebrow="ASSETS"
    title="资产库管理"
    description="统一管理角色、场景、道具及其制作分项与生产任务。"
    :icon="Box"
    boundary-text="资产列表、制作分项、主制作人分配和 Excel 导入将在下一批接入真实 API；当前页面不会伪造资产缩略图、状态或数量。"
  />
</template>
