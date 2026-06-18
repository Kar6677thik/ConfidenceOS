import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import useStore from '../store';
import NavBar from '../components/NavBar';
import { worstTrustException, countActiveAlerts } from '../components/navBarUtils';

// Stub WebSocket so store.connect() doesn't throw
beforeEach(() => {
  vi.stubGlobal('WebSocket', class {
    constructor() {}
    close() {}
  });
});

function renderNavBar() {
  return render(
    <MemoryRouter initialEntries={['/runtime']}>
      <NavBar />
    </MemoryRouter>,
  );
}

describe('NavBar role-gated visibility', () => {
  it('hides Studio link for Auditor role', () => {
    useStore.setState({ role: 'Auditor', connected: false, averageConfidence: 0 });
    renderNavBar();
    expect(screen.queryByText('Studio')).toBeNull();
  });

  it('shows Studio link for Engineer role', () => {
    useStore.setState({ role: 'Engineer', connected: false, averageConfidence: 0 });
    renderNavBar();
    expect(screen.getByText('Studio')).toBeInTheDocument();
  });

  it('shows Studio link for Manager role', () => {
    useStore.setState({ role: 'Manager', connected: false, averageConfidence: 0 });
    renderNavBar();
    expect(screen.getByText('Studio')).toBeInTheDocument();
  });

  it('hides Studio link for Operator role', () => {
    useStore.setState({ role: 'Operator', connected: false, averageConfidence: 0 });
    renderNavBar();
    expect(screen.queryByText('Studio')).toBeNull();
  });
});

describe('worstTrustException (unit)', () => {
  it('returns critical status when disconnected', () => {
    const result = worstTrustException([], false);
    expect(result.status).toBe('status-critical');
  });

  it('returns safe status with all HIGH sensors', () => {
    const confidence = [
      { sensor_id: 'A', tier: 'HIGH', confidence_pct: 90, trust_state: 'TRUSTED' },
      { sensor_id: 'B', tier: 'HIGH', confidence_pct: 95, trust_state: 'TRUSTED' },
    ];
    const result = worstTrustException(confidence, true);
    expect(result.status).toBe('status-safe');
    expect(result.label).toMatch(/no active trust exceptions/i);
  });

  it('returns critical status when a QUARANTINED sensor is present', () => {
    const confidence = [
      { sensor_id: 'LT-5100', tier: 'CRITICAL', confidence_pct: 10, trust_state: 'QUARANTINED' },
      { sensor_id: 'FI-2010', tier: 'HIGH', confidence_pct: 90, trust_state: 'TRUSTED' },
    ];
    const result = worstTrustException(confidence, true);
    expect(result.status).toBe('status-critical');
    expect(result.label).toContain('QUARANTINED');
  });

  it('returns warning status for DEGRADED sensor', () => {
    const confidence = [
      { sensor_id: 'PT-100', tier: 'LOW', confidence_pct: 40, trust_state: 'DEGRADED' },
    ];
    const result = worstTrustException(confidence, true);
    expect(result.status).toBe('status-warning');
  });
});

describe('countActiveAlerts (unit)', () => {
  it('returns 0 when all sensors are HIGH and no flags', () => {
    const confidence = [
      { tier: 'HIGH' },
      { tier: 'HIGH' },
    ];
    expect(countActiveAlerts(confidence, null, [])).toBe(0);
  });

  it('counts non-HIGH confidence tiers', () => {
    const confidence = [
      { tier: 'HIGH' },
      { tier: 'MEDIUM' },
      { tier: 'LOW' },
      { tier: 'CRITICAL' },
    ];
    expect(countActiveAlerts(confidence, null, [])).toBe(3);
  });

  it('adds mass balance flags', () => {
    const confidence = [{ tier: 'HIGH' }];
    const massBalance = { flags: ['flag1', 'flag2'] };
    expect(countActiveAlerts(confidence, massBalance, [])).toBe(2);
  });

  it('adds stale flags', () => {
    const confidence = [{ tier: 'HIGH' }];
    expect(countActiveAlerts(confidence, null, ['stale1'])).toBe(1);
  });

  it('sums all three alert sources', () => {
    const confidence = [{ tier: 'CRITICAL' }, { tier: 'HIGH' }];
    const massBalance = { flags: ['f1'] };
    const staleFlags = ['s1', 's2'];
    expect(countActiveAlerts(confidence, massBalance, staleFlags)).toBe(4);
  });
});
