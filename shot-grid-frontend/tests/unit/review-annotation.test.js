import assert from 'node:assert/strict'
import test from 'node:test'
import { createAnnotation, createReviewDraft, guardVersionSwitch, prepareDraftSubmission, restorePoint, seekVideoAtMs } from '../../src/components/review/annotationDraft.js'

test('不同显示尺寸按归一化坐标准确恢复', () => {
  const annotation = createAnnotation({ annotationType: 'point', color: '#FF0000', points: [{ x: 960, y: 540 }], naturalWidth: 1920, naturalHeight: 1080 })
  assert.deepEqual(annotation.points[0], { x: 0.5, y: 0.5 })
  assert.deepEqual(restorePoint(annotation.points[0], 640, 360), { x: 320, y: 180 })
})

test('视频批注跳转到确定的整数毫秒位置', () => {
  const video = { currentTime: 0 }
  seekVideoAtMs(video, 1234.9)
  assert.equal(video.currentTime, 1.234)
})

test('版本切换可取消并阻止旧草稿提交到新版本', async () => {
  const draft = createReviewDraft(1)
  draft.content = '待提交'
  assert.equal(await guardVersionSwitch(draft, 2, async () => false), null)
  assert.throws(() => prepareDraftSubmission(draft, 2), /草稿版本已变化/)
  assert.equal((await guardVersionSwitch(draft, 2, async () => true)).versionId, '2')
})
