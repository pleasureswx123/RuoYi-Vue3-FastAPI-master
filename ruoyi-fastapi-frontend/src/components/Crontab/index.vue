<template>
    <div>
        <el-tabs type="border-card">
            <el-tab-pane label="秒" v-if="shouldHide('second')">
                <CrontabSecond
                    @update="updateCrontabValue"
                    :check="checkNumber"
                    :cron="crontabValueObj"
                    ref="cronsecond"
                />
            </el-tab-pane>

            <el-tab-pane label="分钟" v-if="shouldHide('min')">
                <CrontabMin
                    @update="updateCrontabValue"
                    :check="checkNumber"
                    :cron="crontabValueObj"
                    ref="cronmin"
                />
            </el-tab-pane>

            <el-tab-pane label="小时" v-if="shouldHide('hour')">
                <CrontabHour
                    @update="updateCrontabValue"
                    :check="checkNumber"
                    :cron="crontabValueObj"
                    ref="cronhour"
                />
            </el-tab-pane>

            <el-tab-pane label="日" v-if="shouldHide('day')">
                <CrontabDay
                    @update="updateCrontabValue"
                    :check="checkNumber"
                    :cron="crontabValueObj"
                    ref="cronday"
                />
            </el-tab-pane>

            <el-tab-pane label="月" v-if="shouldHide('month')">
                <CrontabMonth
                    @update="updateCrontabValue"
                    :check="checkNumber"
                    :cron="crontabValueObj"
                    ref="cronmonth"
                />
            </el-tab-pane>

            <el-tab-pane label="周" v-if="shouldHide('week')">
                <CrontabWeek
                    @update="updateCrontabValue"
                    :check="checkNumber"
                    :cron="crontabValueObj"
                    ref="cronweek"
                />
            </el-tab-pane>

            <el-tab-pane label="年" v-if="shouldHide('year')">
                <CrontabYear
                    @update="updateCrontabValue"
                    :check="checkNumber"
                    :cron="crontabValueObj"
                    ref="cronyear"
                />
            </el-tab-pane>
        </el-tabs>

        <div class="popup-main">
            <div class="popup-result">
                <p class="title">时间表达式</p>
                <el-table :data="expressionRows" row-key="id" border size="small" empty-text="暂无表达式">
                    <el-table-column
                        v-for="column in expressionColumns"
                        :key="column.key"
                        :prop="column.key"
                        :label="column.label"
                        min-width="70"
                        align="center"
                        show-overflow-tooltip
                    />
                    <el-table-column prop="expression" label="Cron 表达式" min-width="260" align="center" show-overflow-tooltip />
                </el-table>
            </div>
            <CrontabResult :ex="crontabValueString"></CrontabResult>

            <div class="pop_btn">
                <el-button type="primary" @click="submitFill">确定</el-button>
                <el-button type="warning" @click="clearCron">重置</el-button>
                <el-button @click="hidePopup">取消</el-button>
            </div>
        </div>
    </div>
</template>

<script setup>
import CrontabSecond from "./second.vue"
import CrontabMin from "./min.vue"
import CrontabHour from "./hour.vue"
import CrontabDay from "./day.vue"
import CrontabMonth from "./month.vue"
import CrontabWeek from "./week.vue"
import CrontabYear from "./year.vue"
import CrontabResult from "./result.vue"
const { proxy } = getCurrentInstance()
const emit = defineEmits(['hide', 'fill'])
const props = defineProps({
    hideComponent: {
        type: Array,
        default: () => [],
    },
    expression: {
        type: String,
        default: ""
    }
})
const expressionColumns = [
    { key: 'second', label: '秒' },
    { key: 'min', label: '分钟' },
    { key: 'hour', label: '小时' },
    { key: 'day', label: '日' },
    { key: 'month', label: '月' },
    { key: 'week', label: '周' },
    { key: 'year', label: '年' }
]
const tabActive = ref(0)
const hideComponent = ref([])
const expression = ref('')
const crontabValueObj = ref({
    second: "*",
    min: "*",
    hour: "*",
    day: "*",
    month: "*",
    week: "?",
    year: "",
})
const crontabValueString = computed(() => {
    const obj = crontabValueObj.value
    return obj.second
        + " "
        + obj.min
        + " "
        + obj.hour
        + " "
        + obj.day
        + " "
        + obj.month
        + " "
        + obj.week
        + (obj.year === "" ? "" : " " + obj.year)
})
const expressionRows = computed(() => [{
    id: 'current',
    ...crontabValueObj.value,
    expression: crontabValueString.value
}])
watch(expression, () => resolveExp())
function shouldHide(key) {
    return !(hideComponent.value && hideComponent.value.includes(key))
}
function resolveExp() {
    // 反解析 表达式
    if (expression.value) {
        const arr = expression.value.split(/\s+/)
        if (arr.length >= 6) {
            //6 位以上是合法表达式
            let obj = {
                second: arr[0],
                min: arr[1],
                hour: arr[2],
                day: arr[3],
                month: arr[4],
                week: arr[5],
                year: arr[6] ? arr[6] : ""
            }
            crontabValueObj.value = {
                ...obj,
            }
        }
    } else {
        // 没有传入的表达式 则还原
        clearCron()
    }
}
// tab切换值
function tabCheck(index) {
    tabActive.value = index
}
// 由子组件触发，更改表达式组成的字段值
function updateCrontabValue(name, value, from) {
    crontabValueObj.value[name] = value
}
// 表单选项的子组件校验数字格式（通过-props传递）
function checkNumber(value, minLimit, maxLimit) {
    // 检查必须为整数
    value = Math.floor(value)
    if (value < minLimit) {
        value = minLimit
    } else if (value > maxLimit) {
        value = maxLimit
    }
    return value
}
// 隐藏弹窗
function hidePopup() {
    emit("hide")
}
// 填充表达式
function submitFill() {
    emit("fill", crontabValueString.value)
    hidePopup()
}
function clearCron() {
    // 还原选择项
    crontabValueObj.value = {
        second: "*",
        min: "*",
        hour: "*",
        day: "*",
        month: "*",
        week: "?",
        year: "",
    }
}
onMounted(() => {
    expression.value = props.expression
    hideComponent.value = props.hideComponent
})
</script>

<style lang="scss" scoped>
.pop_btn {
    text-align: center;
    margin-top: 20px;
}
.popup-main {
    position: relative;
    margin: 10px auto;
    border-radius: 5px;
    font-size: 12px;
    overflow: hidden;
}
.popup-title {
    overflow: hidden;
    line-height: 34px;
    padding-top: 6px;
    background: #f2f2f2;
}
.popup-result {
    box-sizing: border-box;
    line-height: 24px;
    margin: 25px auto;
    padding: 15px 10px 10px;
    border: 1px solid var(--el-border-color);
    position: relative;
}
.popup-result .title {
    position: absolute;
    top: -28px;
    left: 50%;
    width: 140px;
    font-size: 14px;
    margin-left: -70px;
    text-align: center;
    line-height: 30px;
    background: var(--el-bg-color);
}
.popup-result-scroll {
    font-size: 12px;
    line-height: 24px;
    height: 10em;
    overflow-y: auto;
}
</style>
