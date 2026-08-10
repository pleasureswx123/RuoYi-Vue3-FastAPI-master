<script setup>
import { Film, FolderOpened, House, SwitchButton } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/modules/user'

const router = useRouter()
const userStore = useUserStore()

async function handleLogout() {
  await userStore.signOut()
  await router.replace({ name: 'Login' })
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/workbench"><span>SG</span><strong>Shot Grid</strong></RouterLink>
      <nav aria-label="业务导航">
        <RouterLink to="/workbench"><el-icon><House /></el-icon>工作台</RouterLink>
        <RouterLink to="/projects"><el-icon><FolderOpened /></el-icon>项目</RouterLink>
        <RouterLink to="/files"><el-icon><Film /></el-icon>文件</RouterLink>
      </nav>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div><span class="eyebrow">PRODUCTION WORKSPACE</span><strong>影视制作协作台</strong></div>
        <button class="quiet-button" type="button" @click="handleLogout"><el-icon><SwitchButton /></el-icon>退出</button>
      </header>
      <main><RouterView /></main>
    </div>
  </div>
</template>
