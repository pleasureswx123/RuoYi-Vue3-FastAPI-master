export function createLoadingCounter() {
  let count = 0
  return {
    begin: () => (count += 1),
    end: () => (count = Math.max(0, count - 1)),
    value: () => count
  }
}
