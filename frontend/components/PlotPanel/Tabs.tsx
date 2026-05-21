'use client';

export type TabKey = 'tracking' | 'control' | 'mechanical' | 'power' | 'signal-processing' | 'observer';

export interface TabDef {
  key: TabKey;
  label: string;
}

export function Tabs({ tabs, active, onChange }: { tabs: TabDef[]; active: TabKey; onChange: (k: TabKey) => void }) {
  return (
    <div className="flex border-b border-alva-border bg-alva-panel sticky top-0 z-10">
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => onChange(tab.key)}
            aria-pressed={isActive}
            className={
              'px-4 py-2 text-sm border-r border-alva-border last:border-r-0 transition-colors ' +
              (isActive
                ? 'bg-white text-alva-text border-b-2 border-b-alva-coralDark -mb-px font-medium'
                : 'text-alva-muted hover:text-alva-text hover:bg-white/50 cursor-pointer')
            }
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
