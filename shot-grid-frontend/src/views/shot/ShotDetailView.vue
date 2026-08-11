<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getShot } from '@/api/shot-grid/shots'
import TaskAssignmentPanel from '@/components/task/TaskAssignmentPanel.vue'

const props = defineProps({ shotId: { type: String, required: true } })
const route = useRoute(), projectId = String(route.query.projectId || ''), shot = ref(null)
onMounted(async () => { shot.value = await getShot(projectId, props.shotId) })
</script>
<template>
  <section class="page"><span class="eyebrow">SHOT / {{ shotId }}</span><h1>镜头详情</h1><p v-if="shot" class="lead">{{ shot.description || shot.data?.description }}</p><TaskAssignmentPanel :project-id="projectId" :shot-id="shotId" /></section>
</template>
