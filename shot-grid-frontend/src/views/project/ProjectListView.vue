<script setup>
import { Collection } from '@element-plus/icons-vue'
import BusinessBoundaryView from '@/views/_shared/BusinessBoundaryView.vue'
</script>

<template>
  <BusinessBoundaryView
    eyebrow="PROJECTS"
    title="项目"
    description="项目是集、场次、镜头、资产与成员协作的统一业务边界。"
    :icon="Collection"
    boundary-text="项目列表、创建事务、成员管理和项目范围查询将在下一批通过真实 Shot Grid API 接入；当前页面不生成示例项目或虚构进度。"
  />
</template>
