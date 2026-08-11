import { createApp } from 'vue'

import { ElButton, ElForm, ElFormItem, ElIcon, ElInput, ElTag } from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/icon/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/tag/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from '@/App.vue'
import '@/assets/styles/index.scss'
import { installRouterGuard } from '@/router/guard'
import router from '@/router'
import store from '@/store'

const app = createApp(App)
const globalComponents = [ElButton, ElForm, ElFormItem, ElIcon, ElInput, ElTag]

app.use(store)
app.use(router)
globalComponents.forEach(component => {
  app.component(component.name, component)
})

installRouterGuard(router, store)
app.mount('#app')
