<template>
  <div class="sidebar-logo-container" :class="{ 'collapse': collapse }">
    <router-link class="sidebar-logo-link" to="/" aria-label="返回 Shot Grid 管理平台首页">
      <span class="sidebar-brand-mark" aria-hidden="true">
        <el-icon class="sidebar-brand-icon"><Histogram /></el-icon>
      </span>
      <span v-if="!collapse" class="sidebar-brand-copy">
        <strong>SHOT GRID</strong>
        <small>LAPUTTA · 管理中心</small>
      </span>
    </router-link>
  </div>
</template>

<script setup>
import { Histogram } from '@element-plus/icons-vue'
import useSettingsStore from '@/store/modules/settings'
import variables from '@/assets/styles/variables.module.scss'

defineProps({
  collapse: {
    type: Boolean,
    required: true
  }
})

const settingsStore = useSettingsStore();
const sideTheme = computed(() => settingsStore.sideTheme);

// 获取Logo背景色
const getLogoBackground = computed(() => {
  if (settingsStore.isDark) {
    return 'var(--sidebar-bg)';
  }
  if (settingsStore.navType == 3) {
    return variables.menuLightBg
  }
  return sideTheme.value === 'theme-dark' ? variables.menuBg : variables.menuLightBg;
});

// 获取Logo文字颜色
const getLogoTextColor = computed(() => {
  if (settingsStore.isDark) {
    return 'var(--sidebar-logo-text)'
  }
  if (settingsStore.navType == 3) {
    return variables.menuLightText
  }
  return sideTheme.value === 'theme-dark' ? '#fff' : variables.menuLightText;
});
</script>

<style lang="scss" scoped>
.sidebar-logo-container {
  position: relative;
  width: 200px;
  height: 50px;
  flex: 0 0 200px;
  background: v-bind(getLogoBackground);
  overflow: hidden;

  .sidebar-logo-link {
    display: flex;
    min-width: 0;
    height: 100%;
    width: 100%;
    gap: 10px;
    align-items: center;
    padding: 0 14px;
    box-sizing: border-box;
    color: v-bind(getLogoTextColor);
    line-height: normal;
    text-decoration: none;
    overflow: hidden;
  }

  .sidebar-brand-mark {
    display: flex;
    width: 30px;
    height: 30px;
    flex: 0 0 30px;
    align-items: center;
    justify-content: center;
    padding: 6px;
    box-sizing: border-box;
    background: #f2b84b;
    color: #17130e;
    border-radius: 9px;
    transform: rotate(-2deg);
  }

  .sidebar-brand-icon {
    width: 18px;
    height: 18px;
    font-size: 18px;
  }

  .sidebar-brand-copy {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    justify-content: center;
    min-width: 0;
    line-height: 1.1;
    white-space: nowrap;

    strong,
    small {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    strong {
      font-family: Avenir, "Helvetica Neue", Arial, Helvetica, sans-serif;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.13em;
    }

    small {
      margin-top: 4px;
      color: v-bind(getLogoTextColor);
      font-size: 9px;
      letter-spacing: 0.04em;
      opacity: 0.66;
    }
  }

  &.collapse {
    width: 54px;
    flex-basis: 54px;

    .sidebar-logo-link {
      justify-content: center;
      padding: 0;
    }

    .sidebar-brand-mark {
      transform: none;
    }
  }
}
</style>
