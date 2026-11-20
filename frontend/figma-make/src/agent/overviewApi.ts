// The analyst's brand overview for one week (GET /api/briefing/overview). Every value comes from the server.
const BASE = (import.meta.env.VITE_PHARMAGENTICS_API_BASE_URL || "").trim().replace(/\/+$/, "")

export type Claim = { value: string; raw: number | null; evidence_id: string }
export type Stat = Claim & { key: string; label: string; change: (Claim & { label?: string }) | null; adverse?: boolean }
export type Evidence = { id: string; tool: string; params: Record<string, unknown>; query: string; result: unknown; data_version: string }
export type WeekPoint = { week: string; trx: number; nrx: number; nbrx: number }
export type TerritoryRow = {
  id: string; label: string; status: "material" | "normal" | "no_baseline" | "held_back"
  trx: number | null; change: number | null; gap: number | null; threshold: number | null; impact: number
  series: WeekPoint[]
  health: { status: string; reasons: string[]; missing_keys: number; duplicate_keys: number } | null
  mix: { product: string; name: string; trx: number; share: number | null }[]
  evidence_ids: string[]
}
export type Overview = {
  week: string; first_week: string; latest_week: string; data_version: string; product: string; product_name: string
  weeks: string[]; baseline: string[]; note: string | null
  rule: { material_change: number; material_gap: number; noise_z: number }
  stats: Stat[]; territories: TerritoryRow[]; evidence: Evidence[]
}

export async function getOverview(week?: string, brand = "BXA"): Promise<Overview> {
  if (!BASE) throw new Error("API URL is not configured. Set VITE_PHARMAGENTICS_API_BASE_URL.")
  let response: Response
  const params = new URLSearchParams({ brand_id: brand })
  if (week) params.set("week", week)
  try { response = await fetch(`${BASE}/api/briefing/overview?${params}`, { cache: "no-store", credentials: "same-origin" }) }
  catch { throw new Error("Cannot reach PharmAgentics. Check your connection and try again.") }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body && typeof body.detail === "string" ? body.detail : `Overview request failed (HTTP ${response.status})`
    throw new Error(detail)
  }
  if (!body || typeof body !== "object" || !Array.isArray((body as Overview).territories) || !Array.isArray((body as Overview).stats))
    throw new Error("The overview service answered in an unexpected way.")
  return body as Overview
}
