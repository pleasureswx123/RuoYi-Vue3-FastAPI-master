import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatLogTime } from '../../src/utils/logTime.js'

test('无时区日志保留原时间，不推断为 UTC', () => {
  for (const input of ['2026-10-15 02:19:32', '2026-10-15T02:19:32', '2026-10-15T02:19:32.123456']) {
    assert.equal(formatLogTime(input), '2026-10-15 02:19:32')
  }
})

test('上午登录日志不得被重复加八小时显示为未来时间', () => {
  assert.equal(formatLogTime('2026-10-15T10:31:04'), '2026-10-15 10:31:04')
  assert.equal(formatLogTime('2026-10-15 10:31:04'), '2026-10-15 10:31:04')
})

test('带时区日志按实际时刻转换，避免重复偏移', () => {
  for (const input of ['2026-10-15T02:19:32Z', '2026-10-15T10:19:32+08:00', '2026-10-14T22:19:32-04:00']) {
    assert.equal(formatLogTime(input), '2026-10-15 10:19:32')
  }
})

test('跨日跨年及午夜采用 00 至 23 小时制', () => {
  assert.equal(formatLogTime('2026-12-31T16:00:00Z'), '2027-01-01 00:00:00')
  assert.equal(formatLogTime('2026-10-15T15:59:59Z'), '2026-10-15 23:59:59')
})

test('显示不依赖客户端时区', () => {
  const previous = process.env.TZ
  try {
    for (const zone of ['UTC', 'America/New_York', 'Asia/Shanghai']) {
      process.env.TZ = zone
      assert.equal(formatLogTime('2026-10-15 10:31:04'), '2026-10-15 10:31:04')
      assert.equal(formatLogTime('2026-10-15T02:31:04Z'), '2026-10-15 10:31:04')
    }
  } finally {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  }
})

test('缺失和非法值显示占位符', () => {
  for (const input of [null, undefined, '', ' ', 'invalid', '2026-99-99T02:19:32']) {
    assert.equal(formatLogTime(input), '—')
  }
})
