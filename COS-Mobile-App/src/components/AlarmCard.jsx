import { useEffect, useRef, useState } from 'react';
import PriorityBadge from './PriorityBadge';
import useStore from '../store';

function timeAgo(ts) {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m ago`;
}

const BAND_CLASS = { P1: 'alarm-band-p1', P2: 'alarm-band-p2', P3: 'alarm-band-p3' };
const SWIPE_ACK_THRESHOLD = 90;

export default function AlarmCard({ alarm, onTap }) {
  const acknowledgeAlarm = useStore((s) => s.acknowledgeAlarm);

  // Live timer — re-renders every 30s so "5m ago" ticks forward
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  // Swipe-to-acknowledge
  const startXRef = useRef(null);
  const [swipeX, setSwipeX] = useState(0);
  const [swiping, setSwiping] = useState(false);
  const didSwipeRef = useRef(false);

  const onTouchStart = (e) => {
    if (alarm.acked) return;
    startXRef.current = e.touches[0].clientX;
    didSwipeRef.current = false;
    setSwiping(true);
  };

  const onTouchMove = (e) => {
    if (startXRef.current === null || alarm.acked) return;
    const delta = startXRef.current - e.touches[0].clientX;
    if (delta > 8) {
      didSwipeRef.current = true;
      setSwipeX(Math.min(delta, 130));
    }
  };

  const onTouchEnd = () => {
    if (swipeX >= SWIPE_ACK_THRESHOLD) {
      acknowledgeAlarm(alarm.id);
    }
    setSwipeX(0);
    setSwiping(false);
    startXRef.current = null;
  };

  const handleClick = () => {
    if (didSwipeRef.current) return;
    onTap?.(alarm);
  };

  const swipeProgress = Math.min(swipeX / SWIPE_ACK_THRESHOLD, 1);

  return (
    <div className="alarm-card-wrap">
      {/* Red swipe background */}
      {swipeX > 0 && (
        <div
          className="alarm-swipe-bg"
          style={{ opacity: swipeProgress }}
        >
          <span className="alarm-swipe-label">
            {swipeX >= SWIPE_ACK_THRESHOLD ? '✓ Release to Ack' : '← Ack'}
          </span>
        </div>
      )}

      <div
        className={`alarm-card ${alarm.acked ? 'acked' : ''}`}
        style={{
          transform: `translateX(-${swipeX}px)`,
          transition: swiping ? 'none' : 'transform 0.18s ease',
        }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClick={handleClick}
      >
        <div className={`alarm-card-band ${BAND_CLASS[alarm.priority]}`} />
        <div className="alarm-card-content">
          <div className="alarm-card-top">
            <span className="alarm-tag">{alarm.tag}</span>
            <PriorityBadge priority={alarm.priority} />
            <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 'auto' }}>
              {alarm.area}
            </span>
          </div>
          <div className="alarm-desc">{alarm.desc}</div>
          <div className="alarm-meta">
            <span className="alarm-time">{timeAgo(alarm.raisedAt)}</span>
            {alarm.acked ? (
              <span className="alarm-acked-label">✓ Acknowledged</span>
            ) : (
              <button
                className="alarm-ack-btn"
                onClick={(e) => { e.stopPropagation(); acknowledgeAlarm(alarm.id); }}
              >
                Acknowledge
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
