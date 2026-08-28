<script setup>
defineProps({ asset: { type: Object, required: true }, item: { type: Object, required: true } })
</script>

<template>
  <el-descriptions class="asset-production-info" :column="1" border aria-label="资产完整制作信息">
    <el-descriptions-item label="资产">{{ asset.assetName }}</el-descriptions-item>
    <el-descriptions-item label="制作分项">{{ item.productionItem || '未命名制作分项' }}</el-descriptions-item>
    <el-descriptions-item label="共有说明">{{ asset.description || '未填写' }}</el-descriptions-item>
    <el-descriptions-item v-if="item.description && item.description !== asset.description" label="分项说明">{{ item.description }}</el-descriptions-item>
    <el-descriptions-item v-if="item.remark" label="分项备注">{{ item.remark }}</el-descriptions-item>
  </el-descriptions>
</template>

<style scoped>
.asset-production-info :deep(.el-descriptions__content){white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}.asset-production-info :deep(.el-descriptions__label){width:100px}
</style>
