/**
 * views/CompliancePortal.jsx - Operational Summary Report Generator.
 *
 * This support view is intentionally honest: it creates an operational appendix
 * from ConfidenceOS logs, not a regulatory certification.
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import useStore from '../store';
import PageIdentity from '../components/hmi/PageIdentity';
import SupportViewNotice from '../components/SupportViewNotice';

const REPORT_TYPES = [
  { value: 'full', label: 'Full Operational Appendix' },
  { value: 'alarm', label: 'Collapsed Situation Evidence' },
  { value: 'sensor', label: 'Instrument Trust Evidence' },
  { value: 'handover', label: 'Shift Handover Evidence' },
];

function formatValue(value) {
  if (value === null || value === undefined || value === '') return 'not logged';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value !== 'object') return String(value);
  return summarizeEvidence(value);
}

function titleize(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function summarizeEvidence(value) {
  if (value == null) return 'not logged';
  if (Array.isArray(value)) return `${value.length} row${value.length === 1 ? '' : 's'}`;
  if (typeof value !== 'object') return formatValue(value);
  const preferred = value.title
    || value.name
    || value.sensor_id
    || value.task_id
    || value.state
    || value.status
    || value.action
    || value.description
    || value.message
    || value.note;
  if (preferred) return String(preferred);
  const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && typeof item !== 'object');
  if (!entries.length) return 'structured evidence attached';
  return entries.slice(0, 3).map(([key, item]) => `${titleize(key)}: ${formatValue(item)}`).join(' / ');
}

function sectionLabel(key) {
  const labels = {
    data_coverage: 'Data Coverage',
    runtime_state_at_generation: 'Runtime State At Generation',
    alarm_summary: 'Collapsed Situation / Alarm Evidence',
    sensor_reliability: 'Instrument Trust Evidence',
    shift_handover_log: 'Shift Handover Evidence',
    mass_balance_summary: 'Mass-Balance Evidence',
    field_verification_tasks: 'Field Verification Tasks',
    engineering_assumption_governance: 'Engineering Assumption Governance',
    operational_event_ledger: 'Operational Event Ledger',
    recommendations: 'Deterministic Recommendations',
  };
  return labels[key] || titleize(key);
}

function reportSummary(report) {
  const sections = report?.sections || {};
  const coverage = sections.data_coverage || {};
  const runtime = sections.runtime_state_at_generation || {};
  const alarm = sections.alarm_summary || {};
  const verification = sections.field_verification_tasks || {};
  const massBalance = sections.mass_balance_summary || {};
  const governance = sections.engineering_assumption_governance || report?.assumption_governance || {};
  const governanceSummary = governance.summary || {};
  return [
    {
      label: 'Logged Evidence Rows',
      value: [
        `${coverage.anomaly_rows ?? 0} anomalies`,
        `${coverage.mass_balance_rows ?? 0} mass-balance`,
        `${coverage.verification_task_rows ?? verification.count ?? 0} verification`,
      ].join(' / '),
      status: (coverage.anomaly_rows || coverage.mass_balance_rows || coverage.verification_task_rows) ? 'status-warning' : 'text-[var(--text-muted)]',
    },
    {
      label: 'Runtime Context',
      value: runtime.context_status || 'not evaluated',
      status: ['CRITICAL', 'WARNING', 'MASS_BALANCE_DIVERGENCE'].includes(String(runtime.context_status || '').toUpperCase()) ? 'status-warning' : 'status-safe',
    },
    {
      label: 'Collapsed Situation Evidence',
      value: `${alarm.total_alarms ?? 0} rows / ${massBalance.total_flags ?? 0} mass-balance flags`,
      status: (alarm.total_alarms || massBalance.total_flags) ? 'status-warning' : 'text-[var(--text-muted)]',
    },
    {
      label: 'Handover Gate',
      value: runtime.handover_acceptance || 'not evaluated',
      status: String(runtime.handover_acceptance || '').includes('blocked') ? 'status-critical' : 'text-[var(--text-muted)]',
    },
    {
      label: 'Verification State',
      value: `${verification.active_count ?? 0} active / ${verification.handover_required_count ?? 0} handover-required`,
      status: verification.handover_required_count ? 'status-critical' : 'status-safe',
    },
    {
      label: 'Assumption Governance',
      value: `${governance.status || 'not evaluated'} / ${governanceSummary.stale ?? 0} stale / ${governanceSummary.unapproved ?? 0} unapproved`,
      status: ['WARNING', 'BLOCKING'].includes(String(governance.status || '').toUpperCase()) ? 'status-warning' : 'status-safe',
    },
  ];
}

function EvidenceRows({ value, depth = 0 }) {
  if (Array.isArray(value)) {
    if (!value.length) {
      return <p className="caption-mono text-[var(--text-dim)]">No rows logged in this period.</p>;
    }
    return (
      <div className="space-y-2">
        {value.slice(0, 12).map((item, index) => (
          <div key={`${depth}-${index}`} className="border border-[var(--border)] bg-[var(--surface-panel)] px-3 py-2 min-w-0">
            {typeof item === 'object' && item !== null && (
              <p className="caption-mono text-[var(--text)] font-semibold mb-2 break-words">{summarizeEvidence(item)}</p>
            )}
            <EvidenceRows value={item} depth={depth + 1} />
          </div>
        ))}
        {value.length > 12 && (
          <p className="caption-mono text-[var(--text-dim)]">
            Showing 12 of {value.length} rows. Download PDF for the full report text.
          </p>
        )}
      </div>
    );
  }

  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value);
    if (!entries.length) {
      return <p className="caption-mono text-[var(--text-dim)]">No fields logged.</p>;
    }
    return (
      <div className={depth > 1 ? 'space-y-1' : 'grid grid-cols-1 lg:grid-cols-2 gap-3'}>
        {entries.map(([key, itemValue]) => (
          <div key={key} className={depth > 1 ? 'caption-mono text-[var(--text-muted)] min-w-0' : 'border border-[var(--border)] bg-[var(--surface-panel)] px-3 py-2 min-w-0'}>
            <p className="label-caps text-[var(--text-muted)] mb-1">{titleize(key)}</p>
            {typeof itemValue === 'object' && itemValue !== null ? (
              <EvidenceRows value={itemValue} depth={depth + 1} />
            ) : (
              <p className="caption-mono text-[var(--text)] break-words">{formatValue(itemValue)}</p>
            )}
          </div>
        ))}
      </div>
    );
  }

  return <p className="caption-mono text-[var(--text-muted)]">{formatValue(value)}</p>;
}

export default function CompliancePortal() {
  const navigate = useNavigate();
  const { plantId, role } = useStore();

  useEffect(() => {
    if (!['Manager', 'Auditor'].includes(role)) {
      navigate('/runtime', { replace: true });
    }
  }, [role, navigate]);

  const [hours, setHours] = useState(24);
  const [reportType, setReportType] = useState('full');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const generate = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/compliance/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plant_id: plantId, hours: Number(hours), report_type: reportType }),
      });
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail || `Server error ${res.status}`);
      setReport(payload);
    } catch (err) {
      setError(err.message || 'Report generation failed.');
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!report?.pdf_base64) return;
    const bytes = Uint8Array.from(atob(report.pdf_base64), (char) => char.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = report.pdf_filename || 'confidenceos_operational_summary.pdf';
    link.click();
    URL.revokeObjectURL(url);
  };

  const summary = reportSummary(report);

  return (
    <div className="industrial-page flex overflow-hidden">
      <aside className="w-80 flex flex-col bg-[var(--bg-low)] border-r border-[var(--border)] overflow-y-auto scrollbar-thin">
        <PageIdentity displayName="Compliance Report" level={3} area="Operational Evidence Appendix" />

        <div className="p-5 space-y-5 flex-1">
          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2" htmlFor="report-plant">Plant</label>
            <div id="report-plant" className="industrial-card px-3 py-2 font-data text-[14px] text-[var(--primary)]">
              {plantId?.toUpperCase()}
            </div>
          </div>

          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2" htmlFor="report-hours">Period (hours)</label>
            <input
              id="report-hours"
              type="number"
              value={hours}
              onChange={(event) => setHours(Math.max(1, Number(event.target.value)))}
              className="industrial-input"
              min="1"
              max="8760"
            />
          </div>

          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2" htmlFor="report-type">Report Type</label>
            <select id="report-type" value={reportType} onChange={(event) => setReportType(event.target.value)} className="industrial-select">
              {REPORT_TYPES.map((type) => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={generate}
            disabled={loading}
            className="w-full industrial-control text-[var(--safe-text)] border-[var(--safe-text)]/60 disabled:opacity-40"
          >
            {loading ? 'Generating...' : 'Generate Report'}
          </button>

          <button
            type="button"
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

          <div className="space-y-2 pt-4 border-t border-[var(--border)]">
            <p className="label-caps text-[var(--text-muted)]">Report Boundary</p>
            {[
              'Generated from logged ConfidenceOS data only.',
              'Trust scores are governed rubric values, not calibrated probabilities.',
              'Engineering assumptions show owner role, review due date, approval status, and MOC reference.',
              'Assumption governance is prototype traceability, not a certified safety calculation.',
              'Field verification tasks never restore confidence by themselves.',
              'Unsigned SHA-256 hash provides tamper evidence, not legal certification.',
              'ConfidenceOS remains read-only beside existing DCS/HMI records.',
            ].map((line) => (
              <div key={line} className="flex items-start gap-2">
                <span className="material-symbols-outlined text-[14px] text-[var(--primary)] mt-0.5">check</span>
                <p className="caption-mono text-[var(--text-muted)] leading-relaxed">{line}</p>
              </div>
            ))}
          </div>
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-y-auto scrollbar-thin bg-[var(--bg-base)] p-6">
        <SupportViewNotice
          title="Compliance Report"
          status="support"
          source="Logged anomalies, confidence history, verification tasks, handover briefs, assumption governance, and operational event IDs."
          boundary="This is an operational evidence appendix, not a regulatory certification."
        />
        {!report ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
            <span className="material-symbols-outlined text-[64px] text-[var(--border)]">description</span>
            <p className="text-[18px] font-semibold text-[var(--text-muted)]">No report generated yet</p>
            <p className="caption-mono text-[var(--text-dim)] max-w-sm">
              Generate an operational appendix from logged ConfidenceOS evidence. Empty sections are reported as empty, not invented.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="industrial-card p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h2 className="text-[32px] leading-[36px] font-bold text-[var(--text)]">Operational Summary Report</h2>
                  <p className="caption-mono text-[var(--text-muted)] mt-2">
                    {report.plant_name} / {report.period_hours}h window / {report.included_sections?.length || 0} sections
                  </p>
                  <p className="caption-mono text-[var(--text-dim)] mt-2">
                    Evidence appendix from logged Runtime data. Empty counts mean no source rows were logged, not that the plant was proven healthy.
                  </p>
                </div>
                <span className="industrial-badge text-[var(--text-muted)] border-[var(--border)]">Unsigned</span>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-5 gap-[1px] bg-[var(--border-strong)]">
              {summary.map((item) => (
                <div key={item.label} className="bg-[var(--surface-panel)] border border-[var(--border)] p-4 min-w-0">
                  <p className="label-caps text-[var(--text-muted)]">{item.label}</p>
                  <p className={`caption-mono mt-2 break-words ${item.status}`}>{item.value}</p>
                </div>
              ))}
            </div>

            {report.sections && Object.entries(report.sections).map(([key, section]) => (
              <div key={key} className="industrial-card">
                <div className="industrial-card-header">
                  <p className="text-[14px] font-semibold text-[var(--text)]">{sectionLabel(key)}</p>
                  <p className="caption-mono text-[var(--text-muted)]">{summarizeEvidence(section)}</p>
                </div>
                <div className="p-4">
                  <EvidenceRows value={section} />
                </div>
              </div>
            ))}

            {report.limitations?.length > 0 && (
              <div className="industrial-card p-4 border-[var(--warning)]">
                <p className="label-caps text-[var(--warning)] mb-3">Report limitations</p>
                <EvidenceRows value={report.limitations} />
              </div>
            )}

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
