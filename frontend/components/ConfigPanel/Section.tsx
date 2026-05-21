interface SectionProps {
  title: string;
  children: React.ReactNode;
}

export function Section({ title, children }: SectionProps) {
  return (
    <div className="alva-section">
      <h4>{title}</h4>
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
