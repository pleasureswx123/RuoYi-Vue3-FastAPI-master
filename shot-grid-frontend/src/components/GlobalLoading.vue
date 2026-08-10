<script setup>
import { storeToRefs } from 'pinia'
import { useAppStore } from '@/store/modules/app'

const { loading } = storeToRefs(useAppStore())
</script>

<template>
  <Transition name="fade">
    <div v-if="loading" class="global-loading" role="status" aria-live="polite">
      <span class="global-loading__spinner" />
      <span>正在加载</span>
    </div>
  </Transition>
</template>
