<script setup>import { removeToken } from '@/utils/auth'; removeToken()</script>
<template><main class="error-page"><span class="error-code">401</span><h1>登录已失效</h1><p>会话已过期或被退出，请重新登录。</p><RouterLink class="primary-link" to="/login">重新登录</RouterLink></main></template>
