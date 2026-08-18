import { createApp } from 'vue'

import {
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElDatePicker,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElImage,
  ElInput,
  ElOption,
  ElPagination,
  ElRadioButton,
  ElRadioGroup,
  ElScrollbar,
  ElSelect,
  ElSkeleton,
  ElTable,
  ElTableColumn,
  ElTag
} from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/icon/style/css'
import 'element-plus/es/components/image/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/pagination/style/css'
import 'element-plus/es/components/radio-button/style/css'
import 'element-plus/es/components/radio-group/style/css'
import 'element-plus/es/components/scrollbar/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
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
const globalComponents = [
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElDatePicker,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElImage,
  ElInput,
  ElOption,
  ElPagination,
  ElRadioButton,
  ElRadioGroup,
  ElScrollbar,
  ElSelect,
  ElSkeleton,
  ElTable,
  ElTableColumn,
  ElTag
]

app.use(store)
app.use(router)
globalComponents.forEach(component => {
  app.component(component.name, component)
})

installRouterGuard(router, store)
app.mount('#app')
