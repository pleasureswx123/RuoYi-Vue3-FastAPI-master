<script setup>
import { watch } from 'vue'
import { useSessionStore } from '@/store/modules/session'
import { useRealtimeStore } from '@/store/modules/realtime'

import zhCn from 'element-plus/es/locale/lang/zh-cn'
const session = useSessionStore()
const realtime = useRealtimeStore()
watch(() => session.token, () => realtime.reset())
</script>

<template>
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>
