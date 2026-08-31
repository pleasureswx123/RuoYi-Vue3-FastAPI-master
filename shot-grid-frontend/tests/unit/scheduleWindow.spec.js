import { describe, expect, it } from 'vitest'

import { normalizeScheduleRouteQuery } from '@/views/schedule/scheduleRouteQuery'
import {
  dateRangeToScheduleWindow,
  scheduleWindowForScale,
  scheduleWindowToDateRange
} from '@/views/schedule/scheduleWindow'

describe('排期自然日期窗口', () => {
  it('日视图以今天为锚点显示过去 7 天和未来 23 天', () => {
    expect(scheduleWindowForScale('day', new Date(2026, 7, 31, 16, 20, 30))).toEqual({
      windowStart: '2026-08-24T00:00:00',
      windowEnd: '2026-09-24T00:00:00'
    })
  })

  it('周视图按周一对齐并显示过去 4 周、当前周和未来 8 周', () => {
    expect(scheduleWindowForScale('week', new Date(2026, 7, 31, 16, 20, 30))).toEqual({
      windowStart: '2026-08-03T00:00:00',
      windowEnd: '2026-11-02T00:00:00'
    })
  })

  it('月视图按月初对齐并显示过去 3 个月、当前月和未来 9 个月', () => {
    expect(scheduleWindowForScale('month', new Date(2026, 7, 31, 16, 20, 30))).toEqual({
      windowStart: '2026-05-01T00:00:00',
      windowEnd: '2027-06-01T00:00:00'
    })
  })

  it('日期选择器显示包含结束日的范围，查询仍使用次日零点作为结束边界', () => {
    const window = dateRangeToScheduleWindow(['2026-08-24', '2026-09-23'])

    expect(window).toEqual({
      windowStart: '2026-08-24T00:00:00',
      windowEnd: '2026-09-24T00:00:00'
    })
    expect(scheduleWindowToDateRange(window.windowStart, window.windowEnd)).toEqual([
      '2026-08-24',
      '2026-09-23'
    ])
  })

  it('路由缺少时间时按所选缩放生成默认窗口，显式有效范围保持不变', () => {
    const now = new Date(2026, 7, 31, 16, 20, 30)

    expect(normalizeScheduleRouteQuery({ scale: 'day' }, now)).toMatchObject({
      scale: 'day',
      windowStart: '2026-08-24T00:00:00',
      windowEnd: '2026-09-24T00:00:00'
    })
    expect(normalizeScheduleRouteQuery({
      scale: 'month',
      windowStart: '2025-01-15T09:00:00',
      windowEnd: '2025-03-20T18:00:00'
    }, now)).toMatchObject({
      scale: 'month',
      windowStart: '2025-01-15T09:00:00',
      windowEnd: '2025-03-20T18:00:00'
    })
  })
})
