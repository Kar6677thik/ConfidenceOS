const now = Date.now();

export const MOCK_ALARMS = [
  {
    id: 'a1',
    tag: 'PT-101',
    desc: 'Pressure high — reactor inlet',
    priority: 'P1',
    area: 'Reactor',
    raisedAt: now - 5 * 60 * 1000,
    acked: false,
  },
  {
    id: 'a2',
    tag: 'FT-203',
    desc: 'Flow deviation — cooling loop',
    priority: 'P2',
    area: 'Utilities',
    raisedAt: now - 22 * 60 * 1000,
    acked: false,
  },
  {
    id: 'a3',
    tag: 'TT-047',
    desc: 'Thermocouple drift detected',
    priority: 'P3',
    area: 'Distillation',
    raisedAt: now - 61 * 60 * 1000,
    acked: false,
  },
];

export const MOCK_INCIDENTS = [
  {
    id: 'i1',
    title: 'Reactor pressure excursion',
    area: 'Reactor',
    severity: 'High',
    openSince: now - 35 * 60 * 1000,
  },
  {
    id: 'i2',
    title: 'Cooling loop flow drop',
    area: 'Utilities',
    severity: 'Medium',
    openSince: now - 80 * 60 * 1000,
  },
];

export const MOCK_HANDOVER_DEBT = [
  {
    id: 'h1',
    topic: 'PT-101 pressure trend — watch for recurrence',
    fromShift: 'Night B',
    urgency: 'High',
  },
];

export const MOCK_TASKS = [
  {
    id: 't1',
    tag: 'PT-101',
    desc: 'Verify calibration after pressure excursion',
    role: 'Maintenance',
    status: 'PENDING',
    dueIn: '2h',
  },
  {
    id: 't2',
    tag: 'FT-203',
    desc: 'Flow transmitter loop check',
    role: 'Maintenance',
    status: 'IN_PROGRESS',
    dueIn: '4h',
  },
  {
    id: 't3',
    tag: 'TT-047',
    desc: 'Thermocouple replacement schedule',
    role: 'Engineer',
    status: 'PENDING',
    dueIn: '8h',
  },
  {
    id: 't4',
    tag: 'LT-089',
    desc: 'Level transmitter verification',
    role: 'Operator',
    status: 'DONE',
    dueIn: null,
  },
];

export const MOCK_HANDOVER = {
  shift: 'Day A',
  supervisor: 'R. Patel',
  startTime: '06:00',
  openItems: [
    {
      text: 'PT-101 alarm acknowledged — investigate root cause before night shift',
      urgency: 'High',
    },
    {
      text: 'FT-203 flow transmitter flagged for maintenance',
      urgency: 'Medium',
    },
    {
      text: 'Scheduled calibration for TT-047 due end of week',
      urgency: 'Low',
    },
  ],
  equipmentStatus: [
    { tag: 'PT-101', area: 'Reactor', status: 'critical' },
    { tag: 'FT-203', area: 'Utilities', status: 'warning' },
    { tag: 'TT-047', area: 'Distillation', status: 'warning' },
    { tag: 'LT-089', area: 'Storage', status: 'safe' },
  ],
  notes:
    'Night shift: reactor pressure fluctuation started around 01:30. Acknowledged per ISA-18.2 procedure. Cooling loop checked — flow drop is real, not transmitter fault. Handover to Day A at 06:00 without incident.',
};

export const DEMO_CREDS = [
  {
    label: 'Operator',
    username: 'operator',
    password: 'ConfidenceOS-Op-2025',
    access: 'Alarms · Incidents · Tasks · Handover',
  },
  {
    label: 'Maintenance',
    username: 'maint',
    password: 'ConfidenceOS-Maint-2025',
    access: 'Alarms · Tasks · Incidents · Handover',
  },
  {
    label: 'Engineer',
    username: 'engineer',
    password: 'ConfidenceOS-Eng-2025',
    access: 'Alarms · Tasks · Incidents · Handover',
  },
  {
    label: 'Manager',
    username: 'manager',
    password: 'ConfidenceOS-Mgr-2025',
    access: 'Alarms · Incidents · Tasks · Handover',
  },
  {
    label: 'Auditor',
    username: 'auditor',
    password: 'ConfidenceOS-Aud-2025',
    access: 'Alarms · Incidents · Handover',
  },
];
