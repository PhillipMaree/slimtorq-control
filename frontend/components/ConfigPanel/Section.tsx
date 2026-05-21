import { HelpHint } from '../HelpHint';
import { HELP } from '@/lib/helpContent';

interface SectionProps {
  title: string;
  helpKey?: string;
  children: React.ReactNode;
}

export function Section({ title, helpKey, children }: SectionProps) {
  return (
    <div className="alva-section">
      <h4 className="flex items-center">
        <span>{title}</span>
        {helpKey ? <HelpHint content={HELP[helpKey]} /> : null}
      </h4>
      {children}
    </div>
  );
}

export function Sub({ stem, sub }: { stem: string; sub: string }) {
  return (
    <span>
      {stem}
      <sub>{sub}</sub>
    </span>
  );
}
