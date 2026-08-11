<script setup>
import { SwitchButton } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/modules/user'
import { useNavigationStore } from '@/store/modules/navigation'
import GlobalSearch from '@/components/GlobalSearch.vue'

const router = useRouter()
const userStore = useUserStore()
const navigationStore = useNavigationStore()

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
        <RouterLink v-for="item in navigationStore.entries" :key="item.routeKey" :to="item.path">{{ item.title }}</RouterLink>
      </nav>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div><span class="eyebrow">PRODUCTION WORKSPACE</span><strong>影视制作协作台</strong></div>
        <GlobalSearch />
        <button class="quiet-button" type="button" @click="handleLogout"><el-icon><SwitchButton /></el-icon>退出</button>
      </header>
      <main><RouterView /></main>
    </div>
  </div>
</template>
