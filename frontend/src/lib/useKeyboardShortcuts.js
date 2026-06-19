import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import useStore from '../store';
import { setMuted, isMuted } from './alarmSound';

const STUDIO_ROLES = new Set(['Engineer', 'Manager']);

export default function useKeyboardShortcuts({ onHelpToggle } = {}) {
  const navigate = useNavigate();
  const role = useStore((s) => s.role);

  // Keep a stable ref so the keydown closure always sees the latest callback
  // without requiring the effect to re-run on every parent render.
  const helpRef = useRef(onHelpToggle);
  useEffect(() => { helpRef.current = onHelpToggle; });

  useEffect(() => {
    function handler(e) {
      const el = document.activeElement;
      if (
        el &&
        (el.tagName === 'INPUT' ||
          el.tagName === 'TEXTAREA' ||
          el.tagName === 'SELECT' ||
          el.isContentEditable)
      ) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      switch (e.key) {
        case '1':
          e.preventDefault();
          navigate('/runtime');
          break;
        case '2':
          e.preventDefault();
          navigate('/handover');
          break;
        case '3':
          if (STUDIO_ROLES.has(role)) { e.preventDefault(); navigate('/studio'); }
          break;
        case '4':
          e.preventDefault();
          navigate('/work-queue');
          break;
        case 'm':
        case 'M':
          e.preventDefault();
          setMuted(!isMuted());
          break;
        case '?':
          e.preventDefault();
          helpRef.current?.();
          break;
        default:
          break;
      }
    }

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [navigate, role]);
}
