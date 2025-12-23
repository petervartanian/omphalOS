export type Artifact = {
  path: string
  size: number
  sha256: string
}

export type RunManifest = {
  run_id: string
  created_at: string
  tool_version: string
  artifacts_root_hash: string
  artifacts: Artifact[]
  reports: Record<string, unknown>
}

export type RunIndexEntry = {
  run_id: string
  created_at: string
  root_hash: string
}
