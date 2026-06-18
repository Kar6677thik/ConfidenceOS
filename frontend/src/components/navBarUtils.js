export function countActiveAlerts(confidence, massBalance, staleFlags) {
  const confidenceAlerts = (confidence || []).filter((item) => item.tier && item.tier !== 'HIGH').length;
  const massAlerts = massBalance?.flags?.length || 0;
  const staleAlerts = staleFlags?.length || 0;
  return confidenceAlerts + massAlerts + staleAlerts;
}

export function worstTrustException(confidence, connected) {
  if (!connected) {
    return { label: 'Live trust state unavailable', status: 'status-critical' };
  }
  const rank = { QUARANTINED: 0, UNAVAILABLE: 1, DEGRADED: 2, SUBSTITUTED: 3, TRUSTED: 4, HIGH: 4 };
  const rows = (confidence || [])
    .map((item) => {
      const fallback = item.tier === 'LOW' || item.tier === 'CRITICAL' ? 'DEGRADED' : item.tier || 'TRUSTED';
      const trust = String(item.trust_state || fallback).toUpperCase();
      return { ...item, trust, rank: rank[trust] ?? 5 };
    })
    .sort((a, b) => a.rank - b.rank || (a.confidence_pct ?? 100) - (b.confidence_pct ?? 100));
  const lead = rows[0];
  if (!lead) {
    return { label: 'Awaiting live trust evidence', status: 'status-caution' };
  }
  if ((lead.rank ?? 5) <= 2) {
    return { label: `${lead.trust} ${lead.sensor_id || ''}`.trim(), status: lead.rank <= 1 ? 'status-critical' : 'status-warning' };
  }
  return { label: 'No active trust exceptions', status: 'status-safe' };
}
