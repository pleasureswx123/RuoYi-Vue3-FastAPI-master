import assert from 'node:assert/strict'
import test from 'node:test'
import { validateSelectedMedia, versionMediaErrorMessage } from '../../src/utils/versionMedia.js'

const imagePolicy = { extensions: ['.jpg', '.jpeg', '.png'], mimeTypes: ['image/jpeg', 'image/png'], maxSizeBytes: 50 * 1024 * 1024 }

test('版本媒体领域错误使用稳定 errorKey 映射', () => {
  assert.match(versionMediaErrorMessage({ errorKey: 'SG_VERSION_TASK_MEDIA_MISMATCH' }), /镜头任务/)
  assert.match(versionMediaErrorMessage({ errorKey: 'SG_VERSION_FILE_SIGNATURE_INVALID' }), /伪装/)
  assert.match(versionMediaErrorMessage({ errorKey: 'SG_VERSION_PRODUCTION_ITEM_REQUIRED' }), /制作分项/)
})

test('文件选择提示同时检查扩展名、浏览器 MIME 和大小', () => {
  assert.match(validateSelectedMedia({ name: 'fake.mp4', type: 'video/mp4', size: 12 }, imagePolicy), /扩展名/)
  assert.match(validateSelectedMedia({ name: 'fake.jpg', type: 'video/mp4', size: 12 }, imagePolicy), /媒体类型/)
  assert.match(validateSelectedMedia({ name: 'huge.png', type: 'image/png', size: 51 * 1024 * 1024 }, imagePolicy), /不超过/)
  assert.equal(validateSelectedMedia({ name: 'ok.jpeg', type: 'image/jpeg', size: 1024 }, imagePolicy), null)
})
