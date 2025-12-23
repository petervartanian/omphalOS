import type { RunIndexEntry, RunManifest } from './types'

export class ApiClient {
  constructor(private readonly baseUrl: string) {}

  async listRuns(): Promise<RunIndexEntry[]> {
    const r = await fetch(`${this.baseUrl}/runs`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return await r.json()
  }

  async readManifest(runId: string): Promise<RunManifest> {
    const r = await fetch(`${this.baseUrl}/runs/${encodeURIComponent(runId)}/manifest`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return await r.json()
  }

  async readText(runId: string, relPath: string): Promise<string> {
    const r = await fetch(`${this.baseUrl}/runs/${encodeURIComponent(runId)}/file?path=${encodeURIComponent(relPath)}`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return await r.text()
  }
}
