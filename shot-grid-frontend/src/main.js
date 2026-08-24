import { createApp } from 'vue'

import { installGlobalComponents } from '@/globalComponents'

import App from '@/App.vue'
import '@/assets/styles/index.scss'
import { installRouterGuard } from '@/router/guard'
import router from '@/router'
import store from '@/store'
import { useThemeStore } from '@/store/modules/theme'

const app = createApp(App)

app.use(store)
app.use(router)
installGlobalComponents(app)
useThemeStore(store).initialize()

installRouterGuard(router, store)
app.mount('#app')
