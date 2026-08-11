export const EMPTY_DRAFT = Object.freeze({ content: '', mediaTimeMs: null, annotations: [] })

export function createReviewDraft(versionId) {
  return { versionId: String(versionId), ...structuredClone(EMPTY_DRAFT) }
}

export function hasReviewDraft(draft) {
  return Boolean(draft?.content.trim() || draft?.mediaTimeMs !== null || draft?.annotations.length)
}

export function normalizePoint(point, naturalWidth, naturalHeight) {
  if (!(naturalWidth > 0 && naturalHeight > 0)) throw new RangeError('媒体自然尺寸必须大于零')
  return {
    x: Math.min(1, Math.max(0, point.x / naturalWidth)),
    y: Math.min(1, Math.max(0, point.y / naturalHeight))
  }
}

export function restorePoint(point, displayWidth, displayHeight) {
  return { x: point.x * displayWidth, y: point.y * displayHeight }
}

export function createAnnotation({ annotationType, color, points, naturalWidth, naturalHeight }) {
  return {
    annotationType,
    color,
    points: points.map(point => normalizePoint(point, naturalWidth, naturalHeight)),
    naturalWidth,
    naturalHeight
  }
}

export function seekVideoAtMs(video, mediaTimeMs) {
  video.currentTime = Math.max(0, Math.trunc(mediaTimeMs)) / 1000
}

export function prepareDraftSubmission(draft, activeVersionId) {
  if (String(draft.versionId) !== String(activeVersionId)) throw new Error('草稿版本已变化，请取消后重新批注')
  return {
    versionId: Number(activeVersionId),
    content: draft.content.trim(),
    mediaTimeMs: draft.mediaTimeMs === null ? null : Math.trunc(draft.mediaTimeMs),
    annotations: structuredClone(draft.annotations)
  }
}

export async function guardVersionSwitch(draft, nextVersionId, confirmDiscard) {
  if (String(draft.versionId) === String(nextVersionId)) return draft
  if (hasReviewDraft(draft) && !(await confirmDiscard())) return null
  return createReviewDraft(nextVersionId)
}

