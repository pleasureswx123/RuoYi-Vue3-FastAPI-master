<script setup>
import { toRef } from 'vue'
import { useProtectedMedia } from './useProtectedMedia'
const props = defineProps({ source: { type: Object, default: null } })
const { objectUrl, loading, error, reload } = useProtectedMedia(toRef(props, 'source'), { range: 'bytes=0-' })
</script>
<template><div class="video-preview"><el-skeleton v-if="loading" animated/><el-alert v-else-if="error" :title="error" type="error" show-icon><el-button @click="reload">重新请求</el-button></el-alert><video v-else-if="objectUrl" :src="objectUrl" controls preload="metadata" @error="reload">当前浏览器无法播放该视频。</video></div></template>
<style scoped>.video-preview video{display:block;width:100%;max-height:65vh;background:#000}</style>
