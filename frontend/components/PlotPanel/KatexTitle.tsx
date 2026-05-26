'use client';

import { useMemo } from 'react';
import katex from 'katex';

export function KatexTitle({ tex, className }: { tex: string; className?: string }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, { throwOnError: false, displayMode: false });
    } catch {
      return tex;
    }
  }, [tex]);
  return <h3 className={`text-sm font-semibold text-alva-text mb-1 ${className ?? ''}`} dangerouslySetInnerHTML={{ __html: html }} />;
}
