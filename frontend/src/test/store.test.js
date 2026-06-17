import { describe, it, expect, beforeEach, vi } from 'vitest';

// Minimal WebSocket mock exposing onmessage/onopen/onclose/onerror
class FakeWS {
  constructor() {
    FakeWS.instance = this;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this.readyState = 1;
  }
  close() {}
  fire(type, data) {
    if (type === 'open' && this.onopen) this.onopen();
    if (type === 'message' && this.onmessage) this.onmessage({ data: JSON.stringify(data) });
    if (type === 'close' && this.onclose) this.onclose();
  }
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', FakeWS);
  // Reset store state between tests by reimporting fresh store
});

describe('store — sensor_update dispatch', async () => {
  it('updates readings, confidence, averageConfidence, chartHistory on sensor_update', async () => {
    const { default: useStore } = await import('../store');

    // Reset to clean slate
    useStore.setState({
      connected: false, _ws: null, _reconnectTimer: null, _intentionalDisconnect: false,
      readings: [], confidence: [], massBalance: null, chartHistory: [],
      averageConfidence: 0, timestamp: null,
    });

    useStore.getState().connect();

    const ws = FakeWS.instance;
    ws.fire('open');

    const sensorUpdate = {
      type: 'sensor_update',
      timestamp: 1000,
      readings: [{ sensor_id: 'TI-100', value: 85.5, unit: 'degC' }],
      confidence: [
        { sensor_id: 'TI-100', confidence_pct: 90, tier: 'HIGH' },
        { sensor_id: 'LT-200', confidence_pct: 60, tier: 'MEDIUM' },
      ],
      mass_balance: { implied_level: 10.1, measured_level: 10.0, discrepancy: 0.1 },
    };

    ws.fire('message', sensorUpdate);

    const state = useStore.getState();
    expect(state.readings).toHaveLength(1);
    expect(state.confidence).toHaveLength(2);
    expect(state.averageConfidence).toBe(75); // (90+60)/2
    expect(state.chartHistory).toHaveLength(1);
    expect(state.chartHistory[0].implied).toBe(10.1);

    useStore.getState().disconnect();
  });

  it('ignores messages with type !== sensor_update', async () => {
    const { default: useStore } = await import('../store');

    useStore.setState({ readings: [], confidence: [], averageConfidence: 0 });
    useStore.getState().connect();
    const ws = FakeWS.instance;
    ws.fire('open');

    ws.fire('message', { type: 'heartbeat', data: 'ping' });

    const state = useStore.getState();
    expect(state.readings).toHaveLength(0);
    expect(state.averageConfidence).toBe(0);

    useStore.getState().disconnect();
  });
});

describe('store — simple reducers', async () => {
  it('selectSensor sets selectedSensorId', async () => {
    const { default: useStore } = await import('../store');
    useStore.getState().selectSensor('TI-100');
    expect(useStore.getState().selectedSensorId).toBe('TI-100');
  });

  it('setRole updates role', async () => {
    const { default: useStore } = await import('../store');
    useStore.getState().setRole('Engineer');
    expect(useStore.getState().role).toBe('Engineer');
    useStore.getState().setRole('Operator');
    expect(useStore.getState().role).toBe('Operator');
  });
});
