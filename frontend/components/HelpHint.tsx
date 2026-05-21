'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import katex from 'katex';

export interface HelpContent {
  title: string;
  body: React.ReactNode;
}

export function Eq({ tex }: { tex: string }) {
  const html = (() => {
    try {
      return katex.renderToString(tex, { throwOnError: false, displayMode: false });
    } catch {
      return tex;
    }
  })();
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

export function BlockEq({ tex }: { tex: string }) {
  const html = (() => {
    try {
      return katex.renderToString(tex, { throwOnError: false, displayMode: true });
    } catch {
      return tex;
    }
  })();
  return <div className="my-2 overflow-x-auto" dangerouslySetInnerHTML={{ __html: html }} />;
}

const POP_WIDTH = 352; // 22rem
const MARGIN = 8;

// Click the (i) → popover renders in a portal at document.body so it floats
// above any scrolling parent (the ConfigPanel uses overflow-y-auto, which
// would otherwise clip the popover). Position is computed in viewport coords
// from the icon's getBoundingClientRect and clamped to stay on-screen.
export function HelpHint({ content }: { content: HelpContent | undefined }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; maxHeight: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const popRef = useRef<HTMLDivElement | null>(null);

  const recompute = () => {
    if (!btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    // Prefer to anchor to the right of the icon; flip to left if no room.
    const wantLeft = r.right + MARGIN;
    const left = wantLeft + POP_WIDTH + MARGIN > vw ? Math.max(MARGIN, r.left - POP_WIDTH - MARGIN) : wantLeft;
    // Vertical: align to icon top, but clamp so the popover stays in viewport.
    const desiredTop = r.top;
    const maxHeight = vh - 2 * MARGIN;
    const top = Math.min(Math.max(MARGIN, desiredTop), vh - MARGIN - 40);
    setPos({ top, left, maxHeight });
  };

  useLayoutEffect(() => {
    if (open) recompute();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!popRef.current || !btnRef.current) return;
      const t = e.target as Node;
      if (!popRef.current.contains(t) && !btnRef.current.contains(t)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onResize = () => recompute();
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', onResize);
    window.addEventListener('scroll', onResize, true);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('scroll', onResize, true);
    };
  }, [open]);

  if (!content) return null;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label={`Help: ${content.title}`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="ml-1 inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-semibold text-alva-muted hover:text-alva-text hover:bg-alva-border/50 cursor-pointer leading-none"
      >
        i
      </button>
      {open && pos && typeof document !== 'undefined'
        ? createPortal(
            <div
              ref={popRef}
              role="dialog"
              style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                width: POP_WIDTH,
                maxHeight: pos.maxHeight,
                overflowY: 'auto',
              }}
              className="z-[1000] bg-white border border-alva-border shadow-lg rounded p-3 text-xs text-alva-text"
            >
              <div className="font-semibold text-sm text-alva-text mb-1">{content.title}</div>
              <div className="space-y-2 leading-relaxed">{content.body}</div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
