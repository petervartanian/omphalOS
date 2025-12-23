export function shortHash(s: string, n = 12): string {
  return s.length <= n ? s : s.slice(0, n)
}
