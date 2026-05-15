package Alva "Alva slotless PMSM + inductive flux encoder models for FOC prototyping"

  block Encoder "Inductive flux encoder: passthrough true, quantized/sampled measured, and wrapped error for mechanical angle and speed.
       Three-harmonic cyclic angle error: theta_err = sum_i A_i * sin(k_i*theta + phi_i)."
    import Modelica.Constants.pi;
    parameter Integer nBits = 22 "Encoder resolution in bits (Zettlex IND-MAX-100: 22)";
    parameter Real thetaOffset(unit = "rad") = 0.0 "Mechanical mounting/calibration offset";
    // H1: eccentricity once-per-rev (~+/-5 arcsec spec)
    // H2: 2nd-order coil/target asymmetry
    // H3: 4th-order per-pole/coupling residual
    parameter Real A1(unit = "rad") = 2.4e-5 "Amplitude of cyclic error, harmonic 1";
    parameter Integer k1 = 1 "Harmonic order 1";
    parameter Real phi1(unit = "rad") = 0.0 "Phase, harmonic 1";
    parameter Real A2(unit = "rad") = 5.0e-6 "Amplitude of cyclic error, harmonic 2";
    parameter Integer k2 = 2 "Harmonic order 2";
    parameter Real phi2(unit = "rad") = 0.0 "Phase, harmonic 2";
    parameter Real A3(unit = "rad") = 1.0e-6 "Amplitude of cyclic error, harmonic 3";
    parameter Integer k3 = 4 "Harmonic order 3";
    parameter Real phi3(unit = "rad") = 0.0 "Phase, harmonic 3";
    parameter Real Ts(unit = "s") = 1e-4 "Encoder sampling time";
    Modelica.Blocks.Interfaces.RealInput theta_m(unit = "rad") "True mechanical rotor angle from the PMSM" annotation(
      Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_true(unit = "rad") "Pass-through true mechanical angle" annotation(
      Placement(transformation(extent = {{100, 70}, {120, 90}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m_true(unit = "rad/s") "True mechanical speed = der(theta_m)" annotation(
      Placement(transformation(extent = {{100, 40}, {120, 60}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_meas(unit = "rad") "Measured mechanical angle wrapped to [0, 2*pi)" annotation(
      Placement(transformation(extent = {{100, 10}, {120, 30}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m_meas(unit = "rad/s") "Sampled measured mechanical speed" annotation(
      Placement(transformation(extent = {{100, -20}, {120, 0}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_err(unit = "rad") "Wrapped angle error (meas - true) in [-pi, pi)" annotation(
      Placement(transformation(extent = {{100, -50}, {120, -30}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m_err(unit = "rad/s") "Speed error (meas - true)" annotation(
      Placement(transformation(extent = {{100, -90}, {120, -70}})));
  protected
    parameter Integer N = integer(2^nBits) "Number of encoder counts";
    parameter Real dTheta = 2*pi/N "Encoder angular resolution [rad/count]";
    discrete Real thetaSampled(start = 0.0);
    discrete Real thetaPrev(start = 0.0);
    discrete Real omegaSampled(start = 0.0);
    Real thetaRaw;
    Real thetaCyclicErr;
    Real thetaQuantized;
  equation
    theta_m_true = theta_m;
    omega_m_true = der(theta_m);
    thetaCyclicErr = A1*sin(k1*theta_m + phi1)
                   + A2*sin(k2*theta_m + phi2)
                   + A3*sin(k3*theta_m + phi3);
    thetaRaw = theta_m + thetaOffset + thetaCyclicErr;
    thetaQuantized = dTheta*floor(thetaRaw/dTheta + 0.5);
    theta_m_meas = mod(thetaQuantized, 2*pi);
    theta_m_err = mod(theta_m_meas - theta_m + pi, 2*pi) - pi;
    omega_m_err = omega_m_meas - omega_m_true;
    when sample(0, Ts) then
      thetaPrev = pre(thetaSampled);
      thetaSampled = theta_m_meas;
      omegaSampled = (mod(thetaSampled - thetaPrev + pi, 2*pi) - pi)/Ts;
    end when;
    omega_m_meas = omegaSampled;
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}), graphics = {
        Rectangle(extent = {{-100, 100}, {100, -100}}, lineColor = {0, 0, 0}, fillColor = {245, 245, 245}, fillPattern = FillPattern.Solid),
        Text(extent = {{-40, 50}, {40, -50}}, textString = "Flux\nEncoder"),
        Text(extent = {{-95, 10}, {-55, -10}}, textString = "theta_m",      horizontalAlignment = TextAlignment.Left),
        Text(extent = {{55, 90},  {95, 70}},  textString = "theta_m_true",  horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 60},  {95, 40}},  textString = "omega_m_true",  horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 30},  {95, 10}},  textString = "theta_m_meas",  horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 0},   {95, -20}}, textString = "omega_m_meas",  horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -30}, {95, -50}}, textString = "theta_m_err",   horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -70}, {95, -90}}, textString = "omega_m_err",   horizontalAlignment = TextAlignment.Right)}));
  end Encoder;

  model PMSM "Surface-PM slotless PMSM with abc-frame boundary. Clarke/Park run internally on the rotor mechanical angle; dq dynamics with Ld = Lq = Ls."
    // ---------- Electrical parameters (Alva STM-105-17-L-4Y) ----------
    parameter Real Rs(unit = "Ohm") = 0.482 "Phase resistance (line-to-neutral)";
    parameter Real Ls(unit = "H") = 10.4e-6 "Synchronous inductance (Ld = Lq for slotless surface-PM)";
    parameter Real psi_m(unit = "Wb") = 4.487e-3 "Permanent magnet flux linkage";
    parameter Integer p = 27 "Number of pole pairs";
    // ---------- Mechanical parameters ----------
    parameter Real J(unit = "kg.m2") = 2.07e-4 "Rotor + load inertia referred to the motor shaft";
    parameter Real B(unit = "N.m.s/rad") = 1.0e-5 "Viscous friction coefficient";
    parameter Real T_load(unit = "N.m") = 0.0 "Constant load torque (positive opposes motion)";
    // ---------- Initial conditions ----------
    parameter Real id0(unit = "A") = 0.0 "Initial d-axis current";
    parameter Real iq0(unit = "A") = 0.0 "Initial q-axis current";
    parameter Real omega_m0(unit = "rad/s") = 0.0 "Initial mechanical speed";
    parameter Real theta_e0(unit = "rad") = 0.0 "Initial electrical angle";
    // ---------- Inputs (phase voltages applied to the motor) ----------
    Modelica.Blocks.Interfaces.RealInput v_a(unit = "V") "Phase-a voltage applied to motor" annotation(
      Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
    Modelica.Blocks.Interfaces.RealInput v_b(unit = "V") "Phase-b voltage applied to motor" annotation(
      Placement(transformation(extent = {{-140, 20}, {-100, 60}})));
    Modelica.Blocks.Interfaces.RealInput v_c(unit = "V") "Phase-c voltage applied to motor" annotation(
      Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    // ---------- Outputs (phase currents and mechanical state) ----------
    Modelica.Blocks.Interfaces.RealOutput i_a(unit = "A") "Phase-a stator current" annotation(
      Placement(transformation(extent = {{100, 70}, {120, 90}})));
    Modelica.Blocks.Interfaces.RealOutput i_b(unit = "A") "Phase-b stator current" annotation(
      Placement(transformation(extent = {{100, 38}, {120, 58}})));
    Modelica.Blocks.Interfaces.RealOutput i_c(unit = "A") "Phase-c stator current" annotation(
      Placement(transformation(extent = {{100, 6}, {120, 26}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m(unit = "rad") "True mechanical rotor angle (unwrapped)" annotation(
      Placement(transformation(extent = {{100, -26}, {120, -6}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m(unit = "rad/s", start = omega_m0) "True mechanical angular speed" annotation(
      Placement(transformation(extent = {{100, -58}, {120, -38}})));
    Modelica.Blocks.Interfaces.RealOutput torque_true(unit = "N.m") "Electromagnetic torque (true)" annotation(
      Placement(transformation(extent = {{100, -90}, {120, -70}})));
  protected
    Real v_alpha(unit = "V") "Clarke alpha-axis stator voltage";
    Real v_beta(unit = "V") "Clarke beta-axis stator voltage";
    Real v_d(unit = "V") "Park d-axis stator voltage";
    Real v_q(unit = "V") "Park q-axis stator voltage";
    Real i_d(unit = "A", start = id0) "d-axis stator current";
    Real i_q(unit = "A", start = iq0) "q-axis stator current";
    Real i_alpha(unit = "A") "Inverse-Park alpha-axis stator current";
    Real i_beta(unit = "A") "Inverse-Park beta-axis stator current";
    Real omega_e(unit = "rad/s") "Electrical angular speed (= p * omega_m)";
    Real theta_e(unit = "rad", start = theta_e0) "Electrical angle (unwrapped)";
  initial equation
    i_d = id0;
    i_q = iq0;
    omega_m = omega_m0;
    theta_e = theta_e0;
  equation
    // Clarke (amplitude-invariant 3->2) on phase voltages.
    v_alpha = (2.0/3.0)*(v_a - 0.5*v_b - 0.5*v_c);
    v_beta = (1.0/sqrt(3.0))*(v_b - v_c);
    // Park on voltages.
    v_d = v_alpha*cos(theta_e) + v_beta*sin(theta_e);
    v_q = -v_alpha*sin(theta_e) + v_beta*cos(theta_e);
    // dq-frame stator voltage equations (Ld = Lq = Ls).
    Ls*der(i_d) = v_d - Rs*i_d + omega_e*Ls*i_q;
    Ls*der(i_q) = v_q - Rs*i_q - omega_e*Ls*i_d - omega_e*psi_m;
    // Electromagnetic torque for non-salient (Ld = Lq) machine.
    torque_true = 1.5*p*psi_m*i_q;
    // Mechanical dynamics.
    J*der(omega_m) = torque_true - B*omega_m - T_load;
    // Angle propagation.
    omega_e = p*omega_m;
    der(theta_e) = omega_e;
    theta_m = theta_e/p;
    // Inverse Park on currents.
    i_alpha = i_d*cos(theta_e) - i_q*sin(theta_e);
    i_beta = i_d*sin(theta_e) + i_q*cos(theta_e);
    // Inverse Clarke on currents.
    i_a = i_alpha;
    i_b = -0.5*i_alpha + (sqrt(3.0)/2.0)*i_beta;
    i_c = -0.5*i_alpha - (sqrt(3.0)/2.0)*i_beta;
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}), graphics = {
        Rectangle(extent = {{-100, 100}, {100, -100}}, lineColor = {0, 0, 0}, fillColor = {245, 245, 245}, fillPattern = FillPattern.Solid),
        Ellipse(extent = {{-50, 50}, {50, -50}}, lineColor = {0, 0, 0}, fillColor = {200, 220, 240}, fillPattern = FillPattern.Solid),
        Text(extent = {{-50, 92}, {50, 64}}, textString = "Slotless\nPMSM"),
        Text(extent = {{-40, 12}, {40, -12}}, textString = "abc"),
        Text(extent = {{-95, 90}, {-55, 70}}, textString = "v_a",         horizontalAlignment = TextAlignment.Left),
        Text(extent = {{-95, 50}, {-55, 30}}, textString = "v_b",         horizontalAlignment = TextAlignment.Left),
        Text(extent = {{-95, 10}, {-55, -10}}, textString = "v_c",        horizontalAlignment = TextAlignment.Left),
        Text(extent = {{55, 90},  {95, 70}},  textString = "i_a",         horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 58},  {95, 38}},  textString = "i_b",         horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 26},  {95, 6}},   textString = "i_c",         horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -6},  {95, -26}}, textString = "theta_m",     horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -38}, {95, -58}}, textString = "omega_m",     horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -70}, {95, -90}}, textString = "torque_true", horizontalAlignment = TextAlignment.Right)}));
  end PMSM;

  model Plant "Plant boundary: abc phase voltages in -> phase currents, encoder mechanical signals, and true torque out.
       Encapsulates PMSM (Clarke/Park internal) and Encoder.
       Defaults: Alva SlimTorq STM-105-17-L-4Y (mid-range slotless PMSM) +
       Zettlex IND-MAX-100 inductive encoder."
    // ---------- Electrical parameters (Alva STM-105-17-L-4Y) ----------
    parameter Real Rs(unit = "Ohm") = 0.482 "Phase resistance (line-to-neutral)";
    parameter Real Ls(unit = "H") = 10.4e-6 "Synchronous inductance (Ld = Lq)";
    parameter Real psi_m(unit = "Wb") = 4.487e-3 "PM flux linkage";
    parameter Integer p = 27 "Pole pairs (54-pole motor)";
    // ---------- Mechanical parameters (Alva STM-105-17-L-4Y rotor only) ----------
    parameter Real J(unit = "kg.m2") = 2.07e-4 "Rotor inertia (~2070 gcm^2 catalog)";
    parameter Real B(unit = "N.m.s/rad") = 1.0e-5 "Viscous friction (low-loss bearings)";
    parameter Real T_load(unit = "N.m") = 0.0 "Constant load torque";
    // ---------- Initial conditions ----------
    parameter Real id0(unit = "A") = 0.0;
    parameter Real iq0(unit = "A") = 0.0;
    parameter Real omega_m0(unit = "rad/s") = 0.0;
    parameter Real theta_e0(unit = "rad") = 0.0;
    // ---------- Encoder parameters (Zettlex IND-MAX-100: 22-bit, +/-5 arcsec) ----------
    parameter Integer n_bits = 22 "Encoder bit resolution";
    parameter Real theta_offset(unit = "rad") = 0.0 "Encoder fixed offset";
    // Three-harmonic cyclic angle error.
    parameter Real A1(unit = "rad") = 2.4e-5 "Cyclic error amplitude, harmonic 1";
    parameter Integer k1 = 1 "Cyclic error harmonic order 1 (eccentricity)";
    parameter Real phi1(unit = "rad") = 0.0 "Cyclic error phase, harmonic 1";
    parameter Real A2(unit = "rad") = 5.0e-6 "Cyclic error amplitude, harmonic 2";
    parameter Integer k2 = 2 "Cyclic error harmonic order 2";
    parameter Real phi2(unit = "rad") = 0.0 "Cyclic error phase, harmonic 2";
    parameter Real A3(unit = "rad") = 1.0e-6 "Cyclic error amplitude, harmonic 3";
    parameter Integer k3 = 4 "Cyclic error harmonic order 3";
    parameter Real phi3(unit = "rad") = 0.0 "Cyclic error phase, harmonic 3";
    parameter Real Ts_enc(unit = "s") = 1e-4 "Encoder sampling time (10 kHz)";
    // ---------- Inputs ----------
    Modelica.Blocks.Interfaces.RealInput v_a(unit = "V") "Phase-a voltage applied to motor" annotation(
      Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
    Modelica.Blocks.Interfaces.RealInput v_b(unit = "V") "Phase-b voltage applied to motor" annotation(
      Placement(transformation(extent = {{-140, 20}, {-100, 60}})));
    Modelica.Blocks.Interfaces.RealInput v_c(unit = "V") "Phase-c voltage applied to motor" annotation(
      Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    // ---------- Outputs ----------
    Modelica.Blocks.Interfaces.RealOutput i_a(unit = "A") "Phase-a stator current" annotation(
      Placement(transformation(extent = {{100, 80}, {120, 100}})));
    Modelica.Blocks.Interfaces.RealOutput i_b(unit = "A") "Phase-b stator current" annotation(
      Placement(transformation(extent = {{100, 60}, {120, 80}})));
    Modelica.Blocks.Interfaces.RealOutput i_c(unit = "A") "Phase-c stator current" annotation(
      Placement(transformation(extent = {{100, 40}, {120, 60}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_true(unit = "rad") "True mechanical rotor angle" annotation(
      Placement(transformation(extent = {{100, 20}, {120, 40}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m_true(unit = "rad/s") "True mechanical speed" annotation(
      Placement(transformation(extent = {{100, 0}, {120, 20}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_meas(unit = "rad") "Measured mechanical angle from flux encoder" annotation(
      Placement(transformation(extent = {{100, -20}, {120, 0}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m_meas(unit = "rad/s") "Measured mechanical speed from flux encoder" annotation(
      Placement(transformation(extent = {{100, -40}, {120, -20}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m_err(unit = "rad") "Wrapped encoder angle error (meas - true)" annotation(
      Placement(transformation(extent = {{100, -60}, {120, -40}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m_err(unit = "rad/s") "Encoder speed error (meas - true)" annotation(
      Placement(transformation(extent = {{100, -80}, {120, -60}})));
    Modelica.Blocks.Interfaces.RealOutput torque_true(unit = "N.m") "True electromagnetic torque" annotation(
      Placement(transformation(extent = {{100, -100}, {120, -80}})));
    // ---------- Internal sub-modules ----------
    PMSM pmsm(Rs = Rs, Ls = Ls, psi_m = psi_m, p = p, J = J, B = B, T_load = T_load, id0 = id0, iq0 = iq0, omega_m0 = omega_m0, theta_e0 = theta_e0);
    Encoder encoder(nBits = n_bits, thetaOffset = theta_offset,
                    A1 = A1, k1 = k1, phi1 = phi1,
                    A2 = A2, k2 = k2, phi2 = phi2,
                    A3 = A3, k3 = k3, phi3 = phi3,
                    Ts = Ts_enc);
  equation
    // Phase voltages in -> PMSM.
    connect(v_a, pmsm.v_a);
    connect(v_b, pmsm.v_b);
    connect(v_c, pmsm.v_c);
    // PMSM phase currents -> plant outputs.
    connect(pmsm.i_a, i_a);
    connect(pmsm.i_b, i_b);
    connect(pmsm.i_c, i_c);
    // PMSM true mechanical angle -> Encoder.
    connect(pmsm.theta_m, encoder.theta_m);
    // Encoder outputs -> plant outputs.
    connect(encoder.theta_m_true, theta_m_true);
    connect(encoder.omega_m_true, omega_m_true);
    connect(encoder.theta_m_meas, theta_m_meas);
    connect(encoder.omega_m_meas, omega_m_meas);
    connect(encoder.theta_m_err, theta_m_err);
    connect(encoder.omega_m_err, omega_m_err);
    // PMSM true torque -> plant output.
    connect(pmsm.torque_true, torque_true);
    annotation(
      experiment(StartTime = 0, StopTime = 0.05, Tolerance = 1e-6),
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}), graphics = {
        Rectangle(extent = {{-100, 100}, {100, -100}}, lineColor = {0, 0, 0}, fillColor = {245, 245, 245}, fillPattern = FillPattern.Solid),
        Ellipse(extent = {{-50, 50}, {50, -50}}, lineColor = {0, 0, 0}, fillColor = {200, 220, 240}, fillPattern = FillPattern.Solid),
        Text(extent = {{-50, 92}, {50, 60}}, textString = "Alva\nPlant"),
        Text(extent = {{-40, 12}, {40, -12}}, textString = "abc"),
        Text(extent = {{-95, 90},  {-55, 70}},  textString = "v_a",          horizontalAlignment = TextAlignment.Left),
        Text(extent = {{-95, 50},  {-55, 30}},  textString = "v_b",          horizontalAlignment = TextAlignment.Left),
        Text(extent = {{-95, 10},  {-55, -10}}, textString = "v_c",          horizontalAlignment = TextAlignment.Left),
        Text(extent = {{55, 100},  {95, 80}},   textString = "i_a",          horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 80},   {95, 60}},   textString = "i_b",          horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 60},   {95, 40}},   textString = "i_c",          horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 40},   {95, 20}},   textString = "theta_m_true", horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 20},   {95, 0}},    textString = "omega_m_true", horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, 0},    {95, -20}},  textString = "theta_m_meas", horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -20},  {95, -40}},  textString = "omega_m_meas", horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -40},  {95, -60}},  textString = "theta_m_err",  horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -60},  {95, -80}},  textString = "omega_m_err",  horizontalAlignment = TextAlignment.Right),
        Text(extent = {{55, -80},  {95, -100}}, textString = "torque_true",  horizontalAlignment = TextAlignment.Right)}));
  end Plant;

end Alva;
