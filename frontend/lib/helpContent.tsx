import type { HelpContent } from '@/components/HelpHint';
import { BlockEq, Eq } from '@/components/HelpHint';

// One registry of help text for the ConfigPanel. Keys follow
// "<scope>:<name>" — sections are "section:foo", fields are "field:foo"
// (matching the SimParams field name). Pass the key to <HelpHint> via the
// `helpKey` prop on Section / NumberField / RadioField / etc.

export const HELP: Record<string, HelpContent> = {
  // ---------- Sections ----------
  'section:motor': {
    title: 'Motor variant',
    body: (
      <>
        <p>Pick one of the catalog SKUs (e.g. <code>STM-130-27-M-4D</code>). Each variant resolves to a flat <code>PmsmModel</code> — phase resistance <Eq tex="R_s" />, synchronous inductance <Eq tex="L_s" />, PM flux <Eq tex="\\psi_m" />, pole pairs <Eq tex="p" />, inertia <Eq tex="J" /> — derived from the catalog (REV1.8 page 35) by <code>CatalogMotor.to_pmsm_model()</code>.</p>
        <p>The selected variant drives all downstream defaults: DC-link voltage (<code>rated_voltage</code>), peak load-torque step (<code>te_peak_1s</code>), and the safe LCL <Eq tex="T_c" /> bound below.</p>
      </>
    ),
  },
  'section:power-stage': {
    title: 'Power stage (inverter + PWM)',
    body: (
      <>
        <p>Three-phase voltage-source inverter parameters. <Eq tex="f_{pwm}" /> sets the PWM carrier; <Eq tex="t_{dead}" /> is the gate-driver blanking interval that suppresses shoot-through. PWM mode selects the zero-sequence injection strategy (linear range vs. switching losses).</p>
      </>
    ),
  },
  'section:filter': {
    title: 'Optional LCL output filter',
    body: (
      <>
        <p>Adds an inverter-side <Eq tex="L_1\\,\\Vert\\,C_f" /> stage in series with the motor inductance to attenuate switching ripple before it reaches the windings. Components are derived from the target corner <Eq tex="f_c" />:</p>
        <BlockEq tex="L_f = L_s/4,\\quad C_f = \\tfrac{1}{(2\\pi f_c)^2 L_f},\\quad R_d = \\tfrac{1}{3}\\sqrt{L_f/C_f}" />
        <p>The LCL is a third-order resonant plant with <Eq tex="\\omega_{res} = \\sqrt{(L_1+L_s)/(L_1 L_s C_f)}" />. Enabling the filter switches the PI tuning path; see the <em>PI tuning</em> popover.</p>
      </>
    ),
  },
  'section:encoder': {
    title: 'Flux encoder (Zettlex IND-MAX defaults)',
    body: (
      <>
        <p>Models a magnetic position encoder with quantisation (<Eq tex="N_{bits}" />), constant offset (<Eq tex="\\theta_{offset}" />), and three deterministic harmonic error components <Eq tex="A_k \\sin(k\\theta + \\varphi_k)" />. Sample period <Eq tex="T_{s,enc}" /> is independent of FOC and PWM clocks.</p>
      </>
    ),
  },
  'section:trajectory': {
    title: 'Load-torque step trajectory',
    body: (
      <>
        <p>Piecewise-constant <Eq tex="T_L^{ref}(t)" />: zero until <Eq tex="t_{step}" />, then jumps to <Eq tex="\\mathrm{step\\,frac} \\cdot T_e^{peak,1s}" /> and holds to <Eq tex="t_{end}" />. <Eq tex="T_f" /> caps the simulation horizon (blank = auto from segment end).</p>
      </>
    ),
  },
  'section:timing': {
    title: 'Simulation timing',
    body: (
      <>
        <p><Eq tex="\\Delta t_{sim}" /> is the inner-loop step the FMU advances (also the PWM-compare resolution and dead-time tracker tick). Default is <Eq tex="T_{pwm}/20" /> — 20 sub-samples per PWM period, which is the de-facto standard for clean carrier resolution.</p>
      </>
    ),
  },
  'section:current-loop': {
    title: 'Current-loop PI tuning',
    body: (
      <>
        <p>Per-axis dq PI in parallel form <Eq tex="C(s) = K_p + K_i/s" />. After FOC decoupling + BEMF feedforward, the plant collapses to a first-order R/L circuit:</p>
        <BlockEq tex="G(s) = \\tfrac{1}{L_s s + R_s}" />
        <p>Three tuning rules pick <Eq tex="(K_p, K_i)" /> from different objectives — see the <em>PI tuning</em> field.</p>
      </>
    ),
  },

  // ---------- Fields ----------
  'field:variant_name': {
    title: 'Motor variant SKU',
    body: <p>Catalog key, e.g. <code>STM-130-27-M-4D</code>: stator OD (mm), axial length (mm), variant (L/M), series turns + winding connection (Y/D). Drives <Eq tex="R_s, L_s, \\psi_m, p, J" /> and the rated voltage / continuous current.</p>,
  },
  'field:f_pwm': {
    title: 'PWM carrier frequency',
    body: (
      <>
        <p>Sets the inverter carrier and (one tick per period) the FOC update rate. Higher <Eq tex="f_{pwm}" /> reduces current ripple and audible noise but raises switching losses and shrinks the usable dead-time fraction.</p>
        <p><strong>Modulus Optimum</strong> ties the loop bandwidth to <Eq tex="\\omega_{mo} = 1/(2T_\\sigma) = f_{pwm}/3" />, so changing <Eq tex="f_{pwm}" /> directly scales the closed-loop bandwidth.</p>
      </>
    ),
  },
  'field:t_dead': {
    title: 'Gate-driver dead-time',
    body: (
      <>
        <p>Blanking interval inserted between high-side OFF and low-side ON (and vice versa) to prevent shoot-through. Typical values 100&nbsp;ns&ndash;2&nbsp;µs depending on the transistor. Larger <Eq tex="t_{dead}" /> distorts the output voltage at low duty (visible as harmonic injection in the FFT).</p>
      </>
    ),
  },
  'field:pwm_mode': {
    title: 'PWM modulation scheme',
    body: (
      <>
        <p>How the duty for each leg is computed from <Eq tex="(v_a^{ref}, v_b^{ref}, v_c^{ref})" />:</p>
        <ul className="list-disc ml-4 space-y-1">
          <li><strong>sine</strong> — naïve <Eq tex="v/V_{dc} + 0.5" />. Linear range <Eq tex="|v| \\le V_{dc}/2" />.</li>
          <li><strong>svpwm</strong> — third-harmonic-injected; extends linear range by ~15%.</li>
          <li><strong>dpwmmax / dpwmmin</strong> — one phase clamped to a rail per cycle; ~33% fewer switching events.</li>
          <li><strong>dpwm1</strong> — alternating clamp (canonical DSVPWM).</li>
          <li><strong>auto</strong> — SVPWM at low load, DPWM1 at high modulation index (hysteresis at <Eq tex="m \\in [0.45, 0.55]" />).</li>
        </ul>
      </>
    ),
  },
  'field:inverter_mode': {
    title: 'Inverter fidelity',
    body: (
      <>
        <ul className="list-disc ml-4 space-y-1">
          <li><strong>ideal</strong> — <Eq tex="v_{abc}^{ref}" /> goes straight to the FMU; no PWM, no dead-time. Use to isolate controller/plant behaviour.</li>
          <li><strong>average</strong> — duty computed but cycle-averaged voltages emitted. Tests duty correctness without switching ripple.</li>
          <li><strong>switching</strong> — real carrier compare + dead-time. Production default.</li>
        </ul>
      </>
    ),
  },
  'field:filter_enabled': {
    title: 'Enable LCL output filter',
    body: (
      <>
        <p>Inserts an inverter-side L+C in series with the motor inductance. Attenuates PWM switching ripple at the motor terminals but adds a resonance that constrains the achievable loop bandwidth — see <strong>f_c</strong> and the <em>PI tuning</em> popover.</p>
        <p>When ON, the sim runs the LCL observer (<Eq tex="\\hat{i}_1, \\hat{i}_m, \\hat{i}_c" />) and the Observer tab becomes available.</p>
      </>
    ),
  },
  'field:filter_fc': {
    title: 'LCL corner frequency',
    body: (
      <>
        <p>Sets the LC corner <Eq tex="f_c = 1/(2\\pi\\sqrt{L_f C_f})" />. Rule-of-thumb placement: well above the loop bandwidth, well below <Eq tex="f_{pwm}" />. Typical: <Eq tex="f_c \\approx f_{pwm}/10" />.</p>
        <p><strong>Why the MO guard trips at default settings.</strong> With <Eq tex="f_{pwm} = 50\\,\\mathrm{kHz}" />, <Eq tex="f_c = 5\\,\\mathrm{kHz}" />, <Eq tex="L_f = L_s/4" />:</p>
        <ul className="list-disc ml-4 space-y-1">
          <li>MO implied BW: <Eq tex="\\omega_{mo} = f_{pwm}/3 \\Rightarrow 2.65\\,\\mathrm{kHz}" /></li>
          <li>LCL resonance: <Eq tex="\\omega_{res} = 2\\pi f_c \\sqrt{1.25} \\Rightarrow 5.59\\,\\mathrm{kHz}" /></li>
          <li>Ratio <Eq tex="\\omega_{mo}/\\omega_{res} \\approx 0.48" />; conservative margin requires <Eq tex="\\le 0.10" /></li>
        </ul>
        <p>When the filter is on, the sim auto-switches to Skogestad against the active-damping plant with a safe <Eq tex="T_c" /> floor — see the <em>PI tuning</em> popover.</p>
      </>
    ),
  },
  'field:pi_mode': {
    title: 'PI tuning rule',
    body: (
      <>
        <ul className="list-disc ml-4 space-y-1">
          <li><strong>Modulus Optimum</strong> — <Eq tex="T_\\sigma = 1.5/f_{pwm}" />, <Eq tex="K_p = L_s/(2T_\\sigma)" />, <Eq tex="K_i = R_s/(2T_\\sigma)" />. Targets a fixed phase margin; bandwidth scales with <Eq tex="f_{pwm}" />.</li>
          <li><strong>Skogestad SIMC</strong> — <Eq tex="K_p = L_s/(T_c + \\tau)" />, <Eq tex="T_i = \\min(L_s/R_s,\\, k_1(T_c+\\tau))" />. <Eq tex="T_c" /> sets the speed/robustness trade.</li>
          <li><strong>Manual</strong> — enter <Eq tex="K_p, K_i" /> directly.</li>
        </ul>
        <p><strong>With LCL filter on:</strong> MO is unsafe at typical <Eq tex="f_c" /> (its implied BW sits at ~0.5·<Eq tex="\\omega_{res}" />). The sim transparently substitutes Skogestad against the <em>active-damping</em> plant (margin&nbsp;5) and floors <Eq tex="T_c" /> at <Eq tex="1.25 \\cdot 5/\\omega_{res} - \\tau" /> for ~25% headroom.</p>
      </>
    ),
  },
  'field:pi_tc': {
    title: 'Skogestad Tc',
    body: (
      <>
        <p>Closed-loop time constant target. Smaller = faster, more aggressive. Blank uses the canonical Skogestad default <Eq tex="T_c = \\tau = 1.5/f_{pwm}" />, giving the fastest robust response for a first-order plant.</p>
        <p>With the LCL filter on, the actual <Eq tex="T_c" /> used is <Eq tex="\\max(T_c,\\,T_c^{safe})" /> where <Eq tex="T_c^{safe}" /> is derived from <Eq tex="\\omega_{res}" />.</p>
      </>
    ),
  },
  'field:pi_k1': {
    title: 'Skogestad k₁',
    body: <p>Integral time multiplier: <Eq tex="T_i = \\min(L_s/R_s,\\, k_1(T_c+\\tau))" />. <Eq tex="k_1 \\approx 1.44" /> is Skogestad&apos;s recommended default (cancels plant zero unless the plant is sluggish, in which case the integrator is sped up by capping at <Eq tex="L_s/R_s" />).</p>,
  },
  'field:Kp': {
    title: 'PI proportional gain (manual)',
    body: <p>Used verbatim only when <strong>pi_mode = manual</strong>. Otherwise overwritten by the selected tuning rule.</p>,
  },
  'field:Ki': {
    title: 'PI integral gain (manual)',
    body: <p>Used verbatim only when <strong>pi_mode = manual</strong>. Otherwise overwritten by the selected tuning rule.</p>,
  },
  'field:n_bits': {
    title: 'Encoder resolution',
    body: <p>Number of bits per electrical revolution. Quantisation noise floor scales as <Eq tex="2^{-N}" />.</p>,
  },
  'field:theta_offset': {
    title: 'Encoder zero offset',
    body: <p>Constant electrical-angle offset between encoder zero and the rotor d-axis. Mis-alignment shows up as steady-state torque ripple and tracking error.</p>,
  },
  'field:ts_enc': {
    title: 'Encoder sample period',
    body: <p>How often the encoder block updates its measurement. Independent of FOC and PWM clocks — use to model staleness or downsampled position feedback.</p>,
  },
  'field:t_end': {
    title: 'Simulation end time',
    body: <p>Total simulated horizon. Trailing 20% is used for the steady-state error metric.</p>,
  },
  'field:t_step': {
    title: 'Load-step time',
    body: <p>When the load-torque reference jumps from 0 to the step value. Pick small enough that you can see the transient settle before <Eq tex="t_{end}" />.</p>,
  },
  'field:t_step_frac': {
    title: 'Load step fraction',
    body: <p>Step amplitude as a fraction of the catalog 1-second peak torque. 1.0 = rated peak; values above 1 will saturate the voltage vector.</p>,
  },
  'field:Tf': {
    title: 'Simulation horizon cap',
    body: <p>Hard cap on the simulator&apos;s internal time horizon. Blank = use trajectory end. Useful when the trajectory has a long tail you don&apos;t want to render.</p>,
  },
  'field:dt_sim': {
    title: 'Inner-loop step',
    body: <p>FMU integration step + PWM-compare resolution + dead-time tracker tick. Blank uses <Eq tex="T_{pwm}/20" /> (standard).</p>,
  },
};
