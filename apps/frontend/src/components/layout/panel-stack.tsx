'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

export interface PanelEntry {
  /** Unique panel identifier */
  id: string;
  /** Panel width in pixels */
  width: number;
  /** Whether this panel is currently open */
  open: boolean;
  /** The panel content — rendered inside a positioned wrapper */
  content: React.ReactNode;
}

interface PanelStackProps {
  /** Array of panels in priority order (first = rightmost when opened first) */
  panels: PanelEntry[];
  /** Called when the backdrop is clicked — should close all panels */
  onCloseAll: () => void;
}

/**
 * PanelStack — Shared slide-out panel orchestrator.
 *
 * Manages positioning, backdrop, and stacking order for multiple
 * right-side slide-out panels (WIR, TIR, Codex, etc.).
 *
 * Rules:
 * - Panels open from the right edge, stacking leftward
 * - The first panel opened sits at right-0, subsequent panels dock to its left
 * - A shared backdrop behind all panels closes everything on click
 * - Each panel's `right` offset is computed from the widths of panels to its right
 */
export function PanelStack({ panels, onCloseAll }: PanelStackProps) {
  // Track the order panels were opened — most recent at end
  const [openOrder, setOpenOrder] = useState<string[]>([]);
  const prevOpenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const currentlyOpen = new Set(panels.filter((p) => p.open).map((p) => p.id));
    const prevOpen = prevOpenRef.current;

    setOpenOrder((prev) => {
      let next = prev.filter((id) => currentlyOpen.has(id)); // Remove closed panels
      // Add newly opened panels to the end (most recent)
      Array.from(currentlyOpen).forEach((id) => {
        if (!prevOpen.has(id) && !next.includes(id)) {
          next.push(id);
        }
      });
      return next;
    });

    prevOpenRef.current = currentlyOpen;
  }, [panels.map((p) => `${p.id}:${p.open}`).join(',')]);

  const anyOpen = openOrder.length > 0;
  if (!anyOpen) return null;

  // Build a map of panel data by id for quick lookup
  const panelMap = new Map(panels.map((p) => [p.id, p]));

  // Compute right offset for each panel in open order.
  // openOrder[0] = first opened = rightmost (right: 0)
  // openOrder[1] = second opened = docked left of first (right: first.width)
  // etc.
  const offsets = new Map<string, number>();
  let cumulative = 0;
  for (const id of openOrder) {
    offsets.set(id, cumulative);
    const panel = panelMap.get(id);
    if (panel) cumulative += panel.width;
  }

  return (
    <>
      {/* Shared backdrop */}
      <div
        className='fixed inset-0 z-[49] bg-black/40 animate-in fade-in duration-200'
        onClick={onCloseAll}
      />

      {/* Render each open panel with computed position */}
      {openOrder.map((id, i) => {
        const panel = panelMap.get(id);
        if (!panel || !panel.open) return null;

        const rightOffset = offsets.get(id) ?? 0;

        return (
          <div
            key={id}
            className={cn(
              'fixed top-0 h-full animate-in slide-in-from-right duration-200',
            )}
            style={{
              right: rightOffset,
              width: panel.width,
              zIndex: 50 + i, // Later panels stack above earlier ones
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {panel.content}
          </div>
        );
      })}
    </>
  );
}
