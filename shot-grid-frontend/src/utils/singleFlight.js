export function createSingleFlight(task) {
  let inflight = null
  return (...args) => {
    if (!inflight) inflight = Promise.resolve().then(() => task(...args)).finally(() => { inflight = null })
    return inflight
  }
}
