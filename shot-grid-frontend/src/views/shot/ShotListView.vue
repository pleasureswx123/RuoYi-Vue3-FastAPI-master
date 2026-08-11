<script setup>
import { Film } from '@element-plus/icons-vue'
import BusinessBoundaryView from '@/views/_shared/BusinessBoundaryView.vue'
</script>

<template>
  <BusinessBoundaryView
    eyebrow="SHOTS"
    title="镜头管理"
    description="围绕集、场次和镜头组织生产任务，并为多视图工作台保留稳定入口。"
    :icon="Film"
    boundary-text="镜头筛选、表格/卡片/故事板视图以及 Excel 预检与正式导入将在下一批接入真实接口；当前页面不回退到本地或 Mock 镜头数据。"
  />
</template>
