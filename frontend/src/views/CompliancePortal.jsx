/**
 * views/CompliancePortal.jsx - Compliance Audit Report Generator
 *
 * Endpoints:
 *   POST /api/compliance/generate - generate report, returns { pdf_base64, sections, ... }
 *
 * Stitch mockup: 4compilance_portal.html
 */

import { useState } from 'react';
import useStore from '../store';
import PageIdentity from '../components/hmi/PageIdentity';

const REPORT_TYPES = [
  { value: 'full',     label: 'Full Audit Report' },
  { value: 'alarm',    label: 'Alarm Management Only' },
  { value: 'sensor',   label: 'Sensor Reliability Only' },
  { value: 'handover', label: 'Shift Handover Log Only' },
];

function formatValue(value) {
  if (value === null || value === undefined || value === '') return 'not logged';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value !== 'object') return String(value);
  return JSON.stringify(value);
}

function DetailRows({ value }) {
  if (Array.isArray(value)) {
    if (!value.length) return <p className="caption-mono text-[var(--text-dim)]">No rows logged in this period.</p>;
    return (
      <div className="space-y-2">
        {value.slice(0, 12).map((item, index) => (
          <div key={index} className="border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
            {typeof item === 'object' && item !== null ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1">
                {Object.entries(item).slice(0, 8).map(([key, itemValue]) => (
                  <p key={key} className="caption-mono text-[var(--text-muted)]">
                    <span className="text-[var(--text-dim)]">{key.replace(/_/g, ' ')}:</span> {formatValue(itemValue)}
                  </p>
                ))}
              </div>
            ) : (
              <p className="caption-mono text-[var(--text-muted)]">{formatValue(item)}</p>
            )}
          </div>
        ))}
        {value.length > 12 && (
          <p className="caption-mono text-[var(--text-dim)]">Showing 12 of {value.length} rows. Download PDF for full report text.</p>
        )}
      </div>
    );
  }

  if (typeof value === 'object' && value !== null) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {Object.entries(value).map(([key, itemValue]) => (
          <div key={key} className="border border-[var(--border)] bg-[var(--surface)] px-3 py-2 min-w-0">
            <p className="label-caps text-[var(--text-muted)] mb-1">{key.replace(/_/g, ' ')}</p>
            <DetailRows value={itemValue} />
          </div>
        ))}
      </div>
    );
  }

  return <p className="caption-mono text-[var(--text-muted)]">{formatValue(value)}</p>;
}

export default function CompliancePortal() {
  const { plantId } = useStore();
  const [hours, setHours]           = useState(24);
  const [reportType, setReportType] = useState('full');
  const [report, setReport]         = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/compliance/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plant_id: plantId, hours: Number(hours), report_type: reportType }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      setReport(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!report?.pdf_base64) return;
    const bytes = Uint8Array.from(atob(report.pdf_base64), (c) => c.charCodeAt(0));
    const url   = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    const a     = document.createElement('a');
    a.href     = url;
    a.download = report.pdf_filename || 'confidenceos_report.pdf';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="industrial-page flex overflow-hidden">

      {/* -- Left sidebar - config panel -- */}
      <aside className="w-80 flex flex-col bg-[var(--bg-low)] border-r border-[var(--border)] overflow-y-auto scrollbar-thin">
        <PageIdentity displayName="Compliance Portal" level={3} area="Operational Summary Report Generator" />

        {/* Config fields */}
        <div className="p-5 space-y-5 flex-1">
          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2">Plant</label>
            <div className="industrial-card px-3 py-2 font-data text-[14px] text-[var(--primary)]">
              {plantId?.toUpperCase()}
            </div>
          </div>

          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2">Period (hours)</label>
            <input
              type="number"
              value={hours}
              onChange={(e) => setHours(Math.max(1, Number(e.target.value)))}
              className="industrial-input"
              min="1" max="8760"
            />
          </div>

          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2">Report Type</label>
            <select value={reportType} onChange={(e) => setReportType(e.target.value)} className="industrial-select">
              {REPORT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <button
            onClick={generate}
            disabled={loading}
            className="w-full industrial-control text-[var(--safe-text)] border-[var(--safe-text)]/60 disabled:opacity-40"
          >
            {loading ? 'Generating...' : 'Generate Report'}
          </button>

          <button
            onClick={download}
            disabled={!report?.pdf_base64}
            className="w-full industrial-control text-[var(--text-muted)] disabled:opacity-30"
          >
            Download PDF
          </button>

          {error && (
            <p className="caption-mono text-[var(--critical)] bg-[rgba(147,0,10,0.1)] px-3 py-2 rounded">
              {error}
            </p>
          )}

          {/* Guidance */}
          <div className="space-y-2 pt-4 border-t border-[var(--border)]">
            <p className="label-caps text-[var(--text-muted)]">What is included</p>
            {[
              'Logged anomaly counts and top contributing sensors',
              'Sensor trust history and calibration age where available',
              'Mass-balance divergence flags captured in the selected window',
              'Shift handover entries recorded by ConfidenceOS',
              'Unsigned SHA-256 content hash and generator provenance',
              'Explicit limitations: trust score is not a calibrated probability',
            ].map((line) => (
              <div key={line} className="flex items-start gap-2">
                <span className="material-symbols-outlined text-[14px] text-[var(--primary)] mt-0.5">check</span>
                <p className="caption-mono text-[var(--text-muted)] leading-relaxed">{line}</p>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* -- Main - report preview -- */}
      <main className="flex-1 min-w-0 overflow-y-auto scrollbar-thin bg-[var(--bg-base)] p-6">
        {!report ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
            <span className="material-symbols-outlined text-[64px] text-[var(--border)]">description</span>
            <p className="text-[18px] font-semibold text-[var(--text-muted)]">No report generated yet</p>
            <p className="caption-mono text-[var(--text-dim)] max-w-sm">
              Configure the parameters on the left and click Generate Report to compile an honest operational appendix from logged ConfidenceOS data.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Report header */}
            <div className="industrial-card p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-[32px] font-bold text-[var(--text)]">Operational Summary Report</h2>
                  <p className="caption-mono text-[var(--text-muted)] mt-2">
                    {report.plant_name} / {report.period_hours}h window / {new Date().toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="industrial-badge text-[var(--text-muted)] border-[var(--border)]">
                    Unsigned
                  </span>
                </div>
              </div>
            </div>

            {/* Sections */}
            {report.sections && Object.entries(report.sections).map(([key, section]) => (
              <div key={key} className="industrial-card">
                <div className="industrial-card-header">
                  <p className="text-[14px] font-semibold text-[var(--text)] capitalize">
                    {key.replace(/_/g, ' ')}
                  </p>
                </div>
                <div className="p-4">
                  <DetailRows value={section} />
                  <div className="hidden">
                  {typeof section === 'object' ? (
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {Object.entries(section).map(([k, v]) => (
                        <div key={k} className="bg-[var(--bg-elevated)] px-3 py-2 rounded">
                          <p className="label-caps text-[var(--text-muted)] mb-1">{k.replace(/_/g, ' ')}</p>
                          <p className="font-data text-[14px] text-[var(--text)]">
                            {(function fmtVal(val) {
                              if (val === null || val === undefined) return '—';
                              if (typeof val === 'number') return Number.isInteger(val) ? val : val.toFixed(2);
                              if (typeof val !== 'object') return String(val);
                              if (Array.isArray(val)) return val.map((item) => (typeof item === 'object' && item !== null ? Object.values(item).join(' / ') : String(item))).join('; ');
                              return Object.entries(val).map(([vk, vv]) => `${vk.replace(/_/g, ' ')}: ${typeof vv === 'object' && vv !== null ? Object.values(vv).join('/') : vv}`).join(' · ');
                            })(v)}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="caption-mono text-[var(--text-muted)]">{String(section)}</p>
                  )}
                  </div>
                </div>
              </div>
            ))}

            {report.limitations?.length > 0 && (
              <div className="industrial-card p-4 border-[var(--warning)]">
                <p className="label-caps text-[var(--warning)] mb-3">Report limitations</p>
                <DetailRows value={report.limitations} />
              </div>
            )}

            {/* Provenance block - tamper-evident content hash, NOT a cryptographic signature */}
            <div className="industrial-card p-4 border-[var(--border)]">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-[var(--text-muted)]">tag</span>
                <div className="min-w-0">
                  <p className="label-caps text-[var(--text-muted)]">Provenance / Unsigned</p>
                  <p className="caption-mono text-[var(--text-muted)] mt-0.5 break-all">
                    SHA-256 {report.provenance?.content_sha256 || 'n/a'}
                  </p>
                  <p className="caption-mono text-[var(--text-dim)] mt-1">
                    {report.provenance?.generator || 'ConfidenceOS Advisory Engine'} / tamper-evident content hash, not a cryptographic signature.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
