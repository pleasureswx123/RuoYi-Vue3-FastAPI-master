<script setup>
import { FolderOpened } from '@element-plus/icons-vue'
import BusinessBoundaryView from '@/views/_shared/BusinessBoundaryView.vue'
</script>

<template>
  <BusinessBoundaryView
    eyebrow="FILES & NAS"
    title="文件与 NAS"
    description="查看受保护业务文件、项目存储绑定与 NAS 目录操作状态。"
    :icon="FolderOpened"
    boundary-text="文件查询、鉴权下载、路径复制和 NAS 操作诊断将在下一批接入真实接口；当前页面不会假装浏览器能够直接打开 UNC 路径。"
  />
</template>
