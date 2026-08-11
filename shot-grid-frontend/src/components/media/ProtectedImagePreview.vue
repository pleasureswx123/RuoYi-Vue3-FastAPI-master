<script setup>
import { computed, ref, toRef } from 'vue'
import { useProtectedMedia } from './useProtectedMedia'

const props = defineProps({ source: { type: Object, default: null }, alt: { type: String, default: '' } })
const scale = ref(1)
const { objectUrl, loading, error, reload } = useProtectedMedia(toRef(props, 'source'))
const imageStyle = computed(() => ({ transform: `scale(${scale.value})` }))
function zoom(delta) { scale.value = Math.min(4, Math.max(0.25, scale.value + delta)) }
</script>
<template><div class="image-preview"><div class="toolbar"><el-button @click="zoom(-0.25)">缩小</el-button><span>{{ Math.round(scale * 100) }}%</span><el-button @click="zoom(0.25)">放大</el-button></div><el-skeleton v-if="loading" animated/><el-alert v-else-if="error" :title="error" type="error"><el-button @click="reload">重试</el-button></el-alert><div v-else class="canvas"><img v-if="objectUrl" :src="objectUrl" :alt="alt" :style="imageStyle" draggable="false"/></div></div></template>
<style scoped>.toolbar{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:10px}.canvas{overflow:auto;display:grid;place-items:center;min-height:260px;background:#101317}.canvas img{max-width:100%;transform-origin:center;transition:transform .15s}.image-preview{min-width:0}</style>
