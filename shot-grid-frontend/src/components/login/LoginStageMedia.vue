<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { VideoPause, VideoPlay } from '@element-plus/icons-vue'

import posterUrl from '@/assets/login/production-stage.webp'
import videoUrl from '@/assets/login/production-stage.mp4'

const videoRef = ref()
const desktop = ref(false)
const reducedMotion = ref(true)
const pageVisible = ref(true)
const userPaused = ref(false)
const autoplayBlocked = ref(false)
const failed = ref(false)
const hasPlayed = ref(false)
const canAnimate = computed(() => desktop.value && !reducedMotion.value && !failed.value)
const motionPaused = computed(() => userPaused.value || autoplayBlocked.value)
let mediaQueries = []
let playAttempt = 0

function wantsPlayback() {
  return canAnimate.value && !userPaused.value && pageVisible.value
}

async function syncPlayback() {
  const attempt = ++playAttempt
  const media = videoRef.value
  if (!media) return
  if (!wantsPlayback()) {
    media.pause()
    return
  }
  // 浏览器拒绝自动播放时保留封面，让用户通过按钮手动播放。
  try {
    media.muted = true
    await media.play()
    if (!wantsPlayback() || media !== videoRef.value) media.pause()
    if (attempt === playAttempt) autoplayBlocked.value = false
  } catch {
    if (attempt === playAttempt) autoplayBlocked.value = true
  }
}

function togglePlayback() {
  userPaused.value = !motionPaused.value
  autoplayBlocked.value = false
  // 点击时直接调用 play，保留浏览器要求的用户手势上下文。
  syncPlayback()
}

function updatePreferences() {
  desktop.value = mediaQueries[0].matches
  reducedMotion.value = mediaQueries[1].matches
  if (!canAnimate.value) hasPlayed.value = false
}

function updateVisibility() {
  pageVisible.value = !document.hidden
}

watch([canAnimate, userPaused, pageVisible], async () => {
  await nextTick()
  syncPlayback()
})

onMounted(() => {
  // 没有媒体查询能力时保留静态封面；小屏幕不会创建 video 或下载视频。
  if (!window.matchMedia) return
  mediaQueries = [
    window.matchMedia('(min-width: 941px)'),
    window.matchMedia('(prefers-reduced-motion: reduce)')
  ]
  mediaQueries.forEach(query => query.addEventListener('change', updatePreferences))
  document.addEventListener('visibilitychange', updateVisibility)
  updateVisibility()
  updatePreferences()
})

onBeforeUnmount(() => {
  playAttempt += 1
  videoRef.value?.pause()
  mediaQueries.forEach(query => query.removeEventListener('change', updatePreferences))
  document.removeEventListener('visibilitychange', updateVisibility)
})
</script>

<template>
  <div class="login-stage-media">
    <div class="login-stage-media__image" :style="{ backgroundImage: `url(${posterUrl})` }">
      <video
        v-if="canAnimate"
        ref="videoRef"
        class="login-stage-media__video"
        :class="{ 'is-visible': hasPlayed }"
        :src="videoUrl"
        :poster="posterUrl"
        muted
        loop
        playsinline
        preload="none"
        aria-hidden="true"
        tabindex="-1"
        disablepictureinpicture
        @playing="hasPlayed = true"
        @error="failed = true"
      ></video>
    </div>
    <el-button
      v-if="canAnimate"
      class="login-stage-media__toggle"
      :icon="motionPaused ? VideoPlay : VideoPause"
      :aria-label="motionPaused ? '播放背景动画' : '暂停背景动画'"
      :aria-pressed="motionPaused"
      size="small"
      round
      @click="togglePlayback"
    >
      {{ motionPaused ? '播放动画' : '暂停动画' }}
    </el-button>
  </div>
</template>

<style scoped lang="scss">
.login-stage-media {
  position: absolute;
  inset: 28px;
  pointer-events: none;
  background: #091117;
}

.login-stage-media__image {
  position: absolute;
  inset: 80px 0 0;
  background-repeat: no-repeat;
  background-position: center top;
  background-size: contain;
}

.login-stage-media__video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center top;
  opacity: 0;
  transition: opacity 500ms ease;

  &.is-visible {
    opacity: 1;
  }
}

.login-stage-media__toggle {
  position: absolute;
  z-index: 4;
  top: 16px;
  right: 16px;
  color: rgba(243, 245, 247, 0.76);
  pointer-events: auto;
  background: rgba(8, 14, 20, 0.6);
  border-color: rgba(243, 245, 247, 0.18);

  &:hover,
  &:focus-visible {
    color: #fff;
    background: rgba(8, 14, 20, 0.9);
    border-color: var(--sg-accent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-stage-media__video {
    transition: none;
  }
}
</style>
