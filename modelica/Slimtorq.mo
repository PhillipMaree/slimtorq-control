package Slimtorq "Slimtorq motor models for Alva-style slotless PMSM control prototyping"

  block Clarke
    "Amplitude-invariant 3->2 Clarke transform. Reusable for currents or voltages."
    Modelica.Blocks.Interfaces.RealInput a
      annotation(Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
    Modelica.Blocks.Interfaces.RealInput b
      annotation(Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    Modelica.Blocks.Interfaces.RealInput c
      annotation(Placement(transformation(extent = {{-140, -100}, {-100, -60}})));
    Modelica.Blocks.Interfaces.RealOutput alpha
      annotation(Placement(transformation(extent = {{100, 40}, {120, 60}})));
    Modelica.Blocks.Interfaces.RealOutput beta
      annotation(Placement(transformation(extent = {{100, -60}, {120, -40}})));
  equation
    alpha = (2.0/3.0) * (a - 0.5*b - 0.5*c);
    beta  = (1.0/sqrt(3.0)) * (b - c);
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}),
        graphics = {
          Rectangle(extent = {{-100, 100}, {100, -100}},
            lineColor = {0, 0, 0}, fillColor = {245, 245, 245},
            fillPattern = FillPattern.Solid),
          Text(extent = {{-80, 30}, {80, -30}}, textString = "Clarke"),
          Text(extent = {{-90, 90}, {-50, 70}},  textString = "i_a",
            horizontalAlignment = TextAlignment.Left),
          Text(extent = {{-90, 10}, {-50, -10}}, textString = "i_b",
            horizontalAlignment = TextAlignment.Left),
          Text(extent = {{-90, -70}, {-50, -90}}, textString = "i_c",
            horizontalAlignment = TextAlignment.Left),
          Text(extent = {{50, 60}, {90, 40}},  textString = "i_alpha",
            horizontalAlignment = TextAlignment.Right),
          Text(extent = {{50, -40}, {90, -60}}, textString = "i_beta",
            horizontalAlignment = TextAlignment.Right)}));
  end Clarke;

  block Park
    "Park transform: stationary alpha-beta to rotating d-q using electrical angle."
    Modelica.Blocks.Interfaces.RealInput alpha
      annotation(Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
    Modelica.Blocks.Interfaces.RealInput beta
      annotation(Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    Modelica.Blocks.Interfaces.RealInput theta_e(unit = "rad")
      annotation(Placement(transformation(extent = {{-140, -100}, {-100, -60}})));
    Modelica.Blocks.Interfaces.RealOutput d
      annotation(Placement(transformation(extent = {{100, 40}, {120, 60}})));
    Modelica.Blocks.Interfaces.RealOutput q
      annotation(Placement(transformation(extent = {{100, -60}, {120, -40}})));
  equation
    d =  alpha*cos(theta_e) + beta*sin(theta_e);
    q = -alpha*sin(theta_e) + beta*cos(theta_e);
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}),
        graphics = {
          Rectangle(extent = {{-100, 100}, {100, -100}},
            lineColor = {0, 0, 0}, fillColor = {245, 245, 245},
            fillPattern = FillPattern.Solid),
          Text(extent = {{-80, 30}, {80, -30}}, textString = "Park")}));
  end Park;

  block InvPark
    "Inverse Park transform: rotating d-q to stationary alpha-beta."
    Modelica.Blocks.Interfaces.RealInput d
      annotation(Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
    Modelica.Blocks.Interfaces.RealInput q
      annotation(Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    Modelica.Blocks.Interfaces.RealInput theta_e(unit = "rad")
      annotation(Placement(transformation(extent = {{-140, -100}, {-100, -60}})));
    Modelica.Blocks.Interfaces.RealOutput alpha
      annotation(Placement(transformation(extent = {{100, 40}, {120, 60}})));
    Modelica.Blocks.Interfaces.RealOutput beta
      annotation(Placement(transformation(extent = {{100, -60}, {120, -40}})));
  equation
    alpha = d*cos(theta_e) - q*sin(theta_e);
    beta  = d*sin(theta_e) + q*cos(theta_e);
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}),
        graphics = {
          Rectangle(extent = {{-100, 100}, {100, -100}},
            lineColor = {0, 0, 0}, fillColor = {245, 245, 245},
            fillPattern = FillPattern.Solid),
          Text(extent = {{-80, 30}, {80, -30}}, textString = "InvPark")}));
  end InvPark;

  block InvClarke
    "Inverse Clarke transform: stationary alpha-beta to 3-phase abc."
    Modelica.Blocks.Interfaces.RealInput alpha
      annotation(Placement(transformation(extent = {{-140, 40}, {-100, 80}})));
    Modelica.Blocks.Interfaces.RealInput beta
      annotation(Placement(transformation(extent = {{-140, -80}, {-100, -40}})));
    Modelica.Blocks.Interfaces.RealOutput a
      annotation(Placement(transformation(extent = {{100, 60}, {120, 80}})));
    Modelica.Blocks.Interfaces.RealOutput b
      annotation(Placement(transformation(extent = {{100, -10}, {120, 10}})));
    Modelica.Blocks.Interfaces.RealOutput c
      annotation(Placement(transformation(extent = {{100, -80}, {120, -60}})));
  equation
    a =  alpha;
    b = -0.5*alpha + (sqrt(3.0)/2.0)*beta;
    c = -0.5*alpha - (sqrt(3.0)/2.0)*beta;
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}),
        graphics = {
          Rectangle(extent = {{-100, 100}, {100, -100}},
            lineColor = {0, 0, 0}, fillColor = {245, 245, 245},
            fillPattern = FillPattern.Solid),
          Text(extent = {{-80, 30}, {80, -30}}, textString = "InvClarke")}));
  end InvClarke;

  block FluxEncoder
    "High-resolution inductive rotor-angle sensor (Zettlex IND-MAX-100 class).
     Models three error mechanisms that dominate FOC angle accuracy:
       - quantization (n_bits)
       - fixed offset (theta_offset)
       - cyclic sinusoidal error A*sin(n*theta + phi)
     Differentiating theta_m_meas to estimate speed amplifies cyclic error to
     A*n*omega -- so the same encoder gets worse as speed rises."

    parameter Integer n_bits = 22
      "Encoder resolution (2^n_bits steps per mechanical revolution)";
    parameter Real theta_offset(unit = "rad") = 0.0
      "Fixed alignment error";
    parameter Real cyclic_amp(unit = "rad") = 0.0
      "Cyclic error amplitude A (IND-MAX-100 ~+/-5 arcsec -> A ~ 2.4e-5 rad)";
    parameter Integer cyclic_order = 1
      "Harmonic order n (1: eccentricity once-per-rev; p: interp. once-per-elec-cycle)";
    parameter Real cyclic_phase(unit = "rad") = 0.0
      "Cyclic error phase offset phi";

    parameter Real step = 2*Modelica.Constants.pi / 2^n_bits
      "Quantization step [rad]";

    Modelica.Blocks.Interfaces.RealInput theta_m_true(unit = "rad")
      annotation(Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_meas(unit = "rad")
      annotation(Placement(transformation(extent = {{100, -10}, {120, 10}})));

    Real e_cyclic(unit = "rad");
    Real theta_raw(unit = "rad");
  equation
    e_cyclic  = cyclic_amp * sin(cyclic_order * theta_m_true + cyclic_phase);
    theta_raw = theta_m_true + theta_offset + e_cyclic;
    theta_m_meas = floor(theta_raw/step + 0.5) * step;
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}),
        graphics = {
          Rectangle(extent = {{-100, 100}, {100, -100}},
            lineColor = {0, 0, 0}, fillColor = {245, 245, 245},
            fillPattern = FillPattern.Solid),
          Text(extent = {{-80, 30}, {80, -30}}, textString = "FluxEncoder")}));
  end FluxEncoder;

  model SlotlessPMSM
    "Surface-PM slotless PMSM in the rotor dq frame (Ld = Lq = Ls)."

    // ---------- Electrical parameters (Alva-like slotless defaults) ----------
    parameter Real Rs(unit = "Ohm") = 0.10
      "Phase resistance (line-to-neutral)";
    parameter Real Ls(unit = "H") = 100e-6
      "Synchronous inductance (Ld = Lq for slotless surface-PM)";
    parameter Real psi_m(unit = "Wb") = 0.005
      "Permanent magnet flux linkage";
    parameter Integer p = 2
      "Number of pole pairs";

    // ---------- Mechanical parameters ----------
    parameter Real J(unit = "kg.m2") = 1.0e-5
      "Rotor + load inertia referred to the motor shaft";
    parameter Real B(unit = "N.m.s/rad") = 1.0e-6
      "Viscous friction coefficient";
    parameter Real T_load(unit = "N.m") = 0.0
      "Constant load torque (positive opposes motion)";

    // ---------- Initial conditions ----------
    parameter Real id0(unit = "A") = 0.0 "Initial d-axis current";
    parameter Real iq0(unit = "A") = 0.0 "Initial q-axis current";
    parameter Real omega_m0(unit = "rad/s") = 0.0 "Initial mechanical speed";
    parameter Real theta_e0(unit = "rad") = 0.0 "Initial electrical angle";

    // ---------- Inputs (dq voltage commands) ----------
    Modelica.Blocks.Interfaces.RealInput ud(unit = "V")
      "d-axis stator voltage command"
      annotation(Placement(transformation(extent = {{-140, 20}, {-100, 60}})));
    Modelica.Blocks.Interfaces.RealInput uq(unit = "V")
      "q-axis stator voltage command"
      annotation(Placement(transformation(extent = {{-140, -60}, {-100, -20}})));

    // ---------- Outputs ----------
    Modelica.Blocks.Interfaces.RealOutput id(unit = "A", start = id0)
      "d-axis stator current"
      annotation(Placement(transformation(extent = {{100, 80}, {120, 100}})));
    Modelica.Blocks.Interfaces.RealOutput iq(unit = "A", start = iq0)
      "q-axis stator current"
      annotation(Placement(transformation(extent = {{100, 50}, {120, 70}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m(unit = "rad/s", start = omega_m0)
      "Mechanical angular speed"
      annotation(Placement(transformation(extent = {{100, 20}, {120, 40}})));
    Modelica.Blocks.Interfaces.RealOutput omega_e(unit = "rad/s")
      "Electrical angular speed (= p * omega_m)"
      annotation(Placement(transformation(extent = {{100, -10}, {120, 10}})));
    Modelica.Blocks.Interfaces.RealOutput theta_e(unit = "rad", start = theta_e0)
      "Electrical angle (unwrapped)"
      annotation(Placement(transformation(extent = {{100, -40}, {120, -20}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_true(unit = "rad")
      "True mechanical rotor angle (= theta_e / p), unwrapped"
      annotation(Placement(transformation(extent = {{100, -70}, {120, -50}})));
    Modelica.Blocks.Interfaces.RealOutput Te(unit = "N.m")
      "Electromagnetic torque"
      annotation(Placement(transformation(extent = {{100, -100}, {120, -80}})));

  initial equation
    id = id0;
    iq = iq0;
    omega_m = omega_m0;
    theta_e = theta_e0;

  equation
    // dq-frame stator voltage equations (Ld = Lq = Ls)
    Ls * der(id) = ud - Rs * id + omega_e * Ls * iq;
    Ls * der(iq) = uq - Rs * iq - omega_e * Ls * id - omega_e * psi_m;

    // Electromagnetic torque for non-salient (Ld = Lq) machine.
    Te = 1.5 * p * psi_m * iq;

    // Mechanical dynamics
    J * der(omega_m) = Te - B * omega_m - T_load;

    // Angle propagation (electrical) and mechanical sensor tap.
    omega_e = p * omega_m;
    der(theta_e) = omega_e;
    theta_m_true = theta_e / p;

    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}),
        graphics = {
          Rectangle(extent = {{-100, 100}, {100, -100}},
            lineColor = {0, 0, 0}, fillColor = {245, 245, 245},
            fillPattern = FillPattern.Solid),
          Ellipse(extent = {{-60, 60}, {60, -60}},
            lineColor = {0, 0, 0}, fillColor = {200, 220, 240},
            fillPattern = FillPattern.Solid),
          Text(extent = {{-80, 92}, {80, 64}}, textString = "Slotless PMSM"),
          Text(extent = {{-40, 12}, {40, -12}}, textString = "PMSM")}));
  end SlotlessPMSM;

  model SlotlessPMSMPlant
    "abc-frame plant: phase voltages in -> phase currents and measured rotor angle out.
     Internally: Clarke + Park on voltages, dq motor model, InvPark + InvClarke
     on currents, FluxEncoder on mechanical angle."

    // ---------- Electrical parameters ----------
    parameter Real Rs(unit = "Ohm") = 0.10
      "Phase resistance (line-to-neutral)";
    parameter Real Ls(unit = "H") = 100e-6
      "Synchronous inductance (Ld = Lq)";
    parameter Real psi_m(unit = "Wb") = 0.005
      "PM flux linkage";
    parameter Integer p = 2
      "Pole pairs";

    // ---------- Mechanical parameters ----------
    parameter Real J(unit = "kg.m2") = 1.0e-5 "Rotor inertia";
    parameter Real B(unit = "N.m.s/rad") = 1.0e-6 "Viscous friction";
    parameter Real T_load(unit = "N.m") = 0.0 "Constant load torque";

    // ---------- Initial conditions ----------
    parameter Real id0(unit = "A") = 0.0;
    parameter Real iq0(unit = "A") = 0.0;
    parameter Real omega_m0(unit = "rad/s") = 0.0;
    parameter Real theta_e0(unit = "rad") = 0.0;

    // ---------- Encoder parameters ----------
    parameter Integer n_bits = 22 "Encoder bit resolution";
    parameter Real theta_offset(unit = "rad") = 0.0 "Encoder fixed offset";
    parameter Real cyclic_amp(unit = "rad") = 0.0 "Cyclic error amplitude";
    parameter Integer cyclic_order = 1 "Cyclic error harmonic order";
    parameter Real cyclic_phase(unit = "rad") = 0.0 "Cyclic error phase";

    // ---------- Inputs ----------
    Modelica.Blocks.Interfaces.RealInput v_a(unit = "V")
      "Phase-a voltage applied to motor"
      annotation(Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
    Modelica.Blocks.Interfaces.RealInput v_b(unit = "V")
      "Phase-b voltage applied to motor"
      annotation(Placement(transformation(extent = {{-140, 20}, {-100, 60}})));
    Modelica.Blocks.Interfaces.RealInput v_c(unit = "V")
      "Phase-c voltage applied to motor"
      annotation(Placement(transformation(extent = {{-140, -20}, {-100, 20}})));

    // ---------- Outputs ----------
    Modelica.Blocks.Interfaces.RealOutput i_a(unit = "A")
      "Measured phase-a current"
      annotation(Placement(transformation(extent = {{100, 80}, {120, 100}})));
    Modelica.Blocks.Interfaces.RealOutput i_b(unit = "A")
      "Measured phase-b current"
      annotation(Placement(transformation(extent = {{100, 50}, {120, 70}})));
    Modelica.Blocks.Interfaces.RealOutput i_c(unit = "A")
      "Measured phase-c current"
      annotation(Placement(transformation(extent = {{100, 20}, {120, 40}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_meas(unit = "rad")
      "Measured mechanical rotor angle from flux encoder"
      annotation(Placement(transformation(extent = {{100, -10}, {120, 10}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m(unit = "rad/s")
      "Mechanical speed (sim-only)"
      annotation(Placement(transformation(extent = {{100, -40}, {120, -20}})));
    Modelica.Blocks.Interfaces.RealOutput Te(unit = "N.m")
      "Electromagnetic torque (sim-only)"
      annotation(Placement(transformation(extent = {{100, -70}, {120, -50}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_true(unit = "rad")
      "True mechanical angle (sim-only, for verification)"
      annotation(Placement(transformation(extent = {{100, -100}, {120, -80}})));

    // ---------- Internal sub-modules ----------
    SlotlessPMSM pmsm(
      Rs = Rs, Ls = Ls, psi_m = psi_m, p = p,
      J = J, B = B, T_load = T_load,
      id0 = id0, iq0 = iq0, omega_m0 = omega_m0, theta_e0 = theta_e0);
    FluxEncoder encoder(
      n_bits = n_bits, theta_offset = theta_offset,
      cyclic_amp = cyclic_amp, cyclic_order = cyclic_order,
      cyclic_phase = cyclic_phase);
    Clarke    clarke_v;
    Park      park_v;
    InvPark   invpark_i;
    InvClarke invclarke_i;

  equation
    // Voltage path: abc -> alpha,beta -> d,q -> motor
    connect(v_a, clarke_v.a)
      annotation(Line(points = {{-100, 80}, {-92, 80}, {-92, 72}, {-85, 72}}));
    connect(v_b, clarke_v.b)
      annotation(Line(points = {{-100, 40}, {-92, 40}, {-92, 60}, {-85, 60}}));
    connect(v_c, clarke_v.c)
      annotation(Line(points = {{-100, 0}, {-92, 0}, {-92, 48}, {-85, 48}}));
    connect(clarke_v.alpha, park_v.alpha)
      annotation(Line(points = {{-55, 68}, {-52, 68}, {-52, 42}, {-50, 42}}));
    connect(clarke_v.beta,  park_v.beta)
      annotation(Line(points = {{-55, 52}, {-52, 52}, {-52, 30}, {-50, 30}}));
    connect(pmsm.theta_e,   park_v.theta_e)
      annotation(Line(points = {{30, -6}, {36, -6}, {36, -30}, {-58, -30}, {-58, 18}, {-50, 18}}));
    connect(park_v.d, pmsm.ud)
      annotation(Line(points = {{-20, 38}, {-15, 38}, {-15, 8}, {-10, 8}}));
    connect(park_v.q, pmsm.uq)
      annotation(Line(points = {{-20, 22}, {-15, 22}, {-15, -8}, {-10, -8}}));

    // Current path: motor d,q -> alpha,beta -> abc
    connect(pmsm.id, invpark_i.d)
      annotation(Line(points = {{30, 18}, {36, 18}, {36, 38}, {40, 38}}));
    connect(pmsm.iq, invpark_i.q)
      annotation(Line(points = {{30, 12}, {36, 12}, {36, 30}, {40, 30}}));
    connect(pmsm.theta_e, invpark_i.theta_e)
      annotation(Line(points = {{30, -6}, {38, -6}, {38, 22}, {40, 22}}));
    connect(invpark_i.alpha, invclarke_i.alpha)
      annotation(Line(points = {{70, 38}, {72, 38}, {72, 69}, {75, 69}}));
    connect(invpark_i.beta,  invclarke_i.beta)
      annotation(Line(points = {{70, 22}, {72, 22}, {72, 51}, {75, 51}}));
    connect(invclarke_i.a, i_a)
      annotation(Line(points = {{95, 70}, {97, 70}, {97, 90}, {100, 90}}));
    connect(invclarke_i.b, i_b)
      annotation(Line(points = {{95, 60}, {100, 60}}));
    connect(invclarke_i.c, i_c)
      annotation(Line(points = {{95, 50}, {97, 50}, {97, 30}, {100, 30}}));

    // Encoder: true mechanical angle -> measured (quantized + offset + cyclic)
    connect(pmsm.theta_m_true, encoder.theta_m_true)
      annotation(Line(points = {{30, -12}, {42, -12}, {42, -40}, {-6, -40}, {-6, -60}, {0, -60}}));
    connect(encoder.theta_m_meas, theta_m_meas)
      annotation(Line(points = {{30, -60}, {60, -60}, {60, 0}, {100, 0}}));

    // Sim-only pass-throughs
    connect(pmsm.omega_m,      omega_m)
      annotation(Line(points = {{30, 6}, {34, 6}, {34, -30}, {100, -30}}));
    connect(pmsm.Te,           Te)
      annotation(Line(points = {{30, -18}, {44, -18}, {44, -60}, {100, -60}}));
    connect(pmsm.theta_m_true, theta_m_true)
      annotation(Line(points = {{30, -12}, {46, -12}, {46, -90}, {100, -90}}));

    annotation(
      experiment(StartTime = 0, StopTime = 0.05, Tolerance = 1e-6),
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}),
        graphics = {
          Rectangle(extent = {{-100, 100}, {100, -100}},
            lineColor = {0, 0, 0}, fillColor = {245, 245, 245},
            fillPattern = FillPattern.Solid),
          Ellipse(extent = {{-60, 60}, {60, -60}},
            lineColor = {0, 0, 0}, fillColor = {200, 220, 240},
            fillPattern = FillPattern.Solid),
          Text(extent = {{-90, 92}, {90, 64}}, textString = "SlotlessPMSMPlant"),
          Text(extent = {{-40, 12}, {40, -12}}, textString = "abc")}),
      Documentation(info = "<html>
        <p>Slotless PMSM plant in the abc frame with realistic sensor outputs.
        Internally instantiates Clarke, Park, SlotlessPMSM (dq), InvPark, InvClarke,
        and FluxEncoder. Use as the FMU boundary for a Python-side FOC controller
        that runs Clarke->Park->PI->InvPark->InvClarke on the measured signals.</p>
      </html>"));
  end SlotlessPMSMPlant;

end Slimtorq;