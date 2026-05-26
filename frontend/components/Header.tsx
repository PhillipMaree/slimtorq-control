import Image from 'next/image';
import type { SimMeta } from '@/types/sim';
import { HelpHint } from './HelpHint';
import { HELP } from '@/lib/helpContent';

export function Header({ meta }: { meta: SimMeta | null }) {
  return (
    <header className="flex items-center gap-4 px-4 py-3 border-b border-alva-border bg-alva-panel">
      <Image src="/logo.png" alt="Alva Industries" width={48} height={48} priority />
      <div className="flex flex-col">
        <span className="font-semibold text-alva-text">SlimTorq Simulator</span>
        <span className="text-sm text-alva-muted">FOC · PWM · Inverter</span>
      </div>
      {meta ? (
        <div className="ml-auto alva-status text-right">
          <div>
            <span className="text-alva-muted">artifact</span> {meta.artifact_name}
          </div>
          <div>
            <span className="text-alva-muted">hash</span> {meta.params_hash}
            <span className="ml-3 text-alva-muted">rows</span> {meta.rows}
            <span className="ml-3 text-alva-muted">err</span> {meta.err_pct.toFixed(2)} %
            <span className="ml-3 text-alva-muted">Kp</span> {meta.foc_kp.toExponential(3)}
            <span className="ml-3 text-alva-muted">Ki</span> {meta.foc_ki.toExponential(3)}
            <span className="ml-3 text-alva-muted">[{meta.pi_mode}]</span>
          </div>
          <div>
            <span className="text-alva-muted">Δiq_pp</span> {meta.iq_ripple.delta_pp.toFixed(2)} A
            <span className="ml-1 text-alva-muted">({meta.iq_ripple.pct_rated.toFixed(1)}% rated)</span>
            <span className="ml-3 text-alva-muted">ΔTe_pp</span> {meta.te_ripple.delta_pp.toFixed(3)} Nm
            <span className="ml-1 text-alva-muted">({meta.te_ripple.pct_rated.toFixed(1)}% rated)</span>
            <span className="ml-3 text-alva-muted">Δia_pp</span> {meta.ia_ripple.delta_pp.toFixed(2)} A
            <span className="ml-1 text-alva-muted">({meta.ia_ripple.pct_rated.toFixed(1)}% rated)</span>
            <span className="ml-2 inline-flex"><HelpHint content={HELP['ripple-stats']} /></span>
          </div>
        </div>
      ) : null}
    </header>
  );
}
