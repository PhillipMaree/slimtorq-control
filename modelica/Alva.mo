package Alva "Alva slotless PMSM + inductive flux encoder models for FOC prototyping"model

  SlotlessPMSM_abc "Surface-PM slotless PMSM with abc-frame boundary for FMU export.
         The external interface is three-phase (v_a, v_b, v_c -> i_a, i_b, i_c) so a
         Python-side FOC controller can run Clarke/Park, encoder modeling, and
         current control. Internally the motor dynamics are still in dq, driven
         by the TRUE rotor electrical angle (no encoder error in this model).
         Balanced three-phase: i_a + i_b + i_c = 0. No neutral wire."
  // ---------- Electrical parameters ----------
    parameter Real R_s(unit = "Ohm") = 0.5 "Phase resistance (line-to-neutral)";
    parameter Real L_s(unit = "H") = 100e-6 "Synchronous inductance (L_d = L_q for slotless surface-PM)";
    parameter Real psi_m(unit = "Wb") = 0.02 "Permanent magnet flux linkage";
    parameter Integer p = 4 "Pole pairs";
    // ---------- Mechanical parameters ----------
    parameter Real J(unit = "kg.m2") = 1e-4 "Rotor inertia";
    parameter Real B(unit = "N.m.s/rad") = 1e-5 "Viscous friction coefficient";
    // ---------- Initial conditions (lowercase: instantaneous quantities at t=0) ----------
    parameter Real i_d0(unit = "A") = 0.0 "Initial d-axis current";
    parameter Real i_q0(unit = "A") = 0.0 "Initial q-axis current";
    parameter Real omega_m0(unit = "rad/s") = 0.0 "Initial mechanical speed";
    parameter Real theta_m0(unit = "rad") = 0.0 "Initial mechanical rotor angle";
    // ---------- Inputs (driven by external Python FOC after InvPark/InvClarke) ----------
    Modelica.Blocks.Interfaces.RealInput v_a(unit = "V") "Phase-a stator voltage" annotation(
      Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
    Modelica.Blocks.Interfaces.RealInput v_b(unit = "V") "Phase-b stator voltage" annotation(
      Placement(transformation(extent = {{-140, 20}, {-100, 60}})));
    Modelica.Blocks.Interfaces.RealInput v_c(unit = "V") "Phase-c stator voltage" annotation(
      Placement(transformation(extent = {{-140, -20}, {-100, 20}})));
    Modelica.Blocks.Interfaces.RealInput T_L(unit = "N.m") "Load torque (positive opposes motion)" annotation(
      Placement(transformation(extent = {{-140, -100}, {-100, -60}})));
    // ---------- Primary outputs (phase currents + mechanical state + torque) ----------
    Modelica.Blocks.Interfaces.RealOutput i_a(unit = "A") "Phase-a stator current" annotation(
      Placement(transformation(extent = {{100, 80}, {120, 100}})));
    Modelica.Blocks.Interfaces.RealOutput i_b(unit = "A") "Phase-b stator current" annotation(
      Placement(transformation(extent = {{100, 60}, {120, 80}})));
    Modelica.Blocks.Interfaces.RealOutput i_c(unit = "A") "Phase-c stator current" annotation(
      Placement(transformation(extent = {{100, 40}, {120, 60}})));
    Modelica.Blocks.Interfaces.RealOutput omega_m(unit = "rad/s", start = omega_m0) "Mechanical angular speed" annotation(
      Placement(transformation(extent = {{100, 20}, {120, 40}})));
    Modelica.Blocks.Interfaces.RealOutput theta_m(unit = "rad", start = theta_m0) "True mechanical rotor angle (unwrapped)" annotation(
      Placement(transformation(extent = {{100, 0}, {120, 20}})));
    Modelica.Blocks.Interfaces.RealOutput T_e(unit = "N.m") "Electromagnetic torque (true)" annotation(
      Placement(transformation(extent = {{100, -20}, {120, 0}})));
    // ---------- Debug outputs (internal dq quantities, for plotting / validation) ----------
    Modelica.Blocks.Interfaces.RealOutput i_d(unit = "A", start = i_d0) "d-axis stator current (internal)" annotation(
      Placement(transformation(extent = {{100, -40}, {120, -20}})));
    Modelica.Blocks.Interfaces.RealOutput i_q(unit = "A", start = i_q0) "q-axis stator current (internal)" annotation(
      Placement(transformation(extent = {{100, -60}, {120, -40}})));
    Modelica.Blocks.Interfaces.RealOutput v_d(unit = "V") "d-axis stator voltage (internal, after Park)" annotation(
      Placement(transformation(extent = {{100, -80}, {120, -60}})));
    Modelica.Blocks.Interfaces.RealOutput v_q(unit = "V") "q-axis stator voltage (internal, after Park)" annotation(
      Placement(transformation(extent = {{100, -100}, {120, -80}})));
  protected
    Real theta_e(unit = "rad") "Electrical angle (= p * theta_m, true rotor angle, no encoder error)";
    Real omega_e(unit = "rad/s") "Electrical angular speed (= p * omega_m)";
    Real v_alpha(unit = "V") "Clarke alpha-axis stator voltage";
    Real v_beta(unit = "V") "Clarke beta-axis stator voltage";
    Real i_alpha(unit = "A") "Inverse-Park alpha-axis stator current";
    Real i_beta(unit = "A") "Inverse-Park beta-axis stator current";
  initial equation
    i_d = i_d0;
    i_q = i_q0;
    omega_m = omega_m0;
    theta_m = theta_m0;
  equation
// ---- Angle propagation (TRUE rotor angle drives the internal Park transform) ----
    omega_e = p*omega_m;
    theta_e = p*theta_m;
// ---- Clarke (amplitude-invariant 3 -> 2) on input phase voltages ----
    v_alpha = (2.0/3.0)*(v_a - 0.5*v_b - 0.5*v_c);
    v_beta = (2.0/3.0)*((sqrt(3.0)/2.0)*v_b - (sqrt(3.0)/2.0)*v_c);
// ---- Park on voltages (true theta_e) ----
    v_d = cos(theta_e)*v_alpha + sin(theta_e)*v_beta;
    v_q = -sin(theta_e)*v_alpha + cos(theta_e)*v_beta;
// ---- dq stator voltage equations (L_d = L_q = L_s) ----
    v_d = R_s*i_d + L_s*der(i_d) - omega_e*L_s*i_q;
    v_q = R_s*i_q + L_s*der(i_q) + omega_e*L_s*i_d + omega_e*psi_m;
// ---- Electromagnetic torque for non-salient (L_d = L_q) machine ----
    T_e = 1.5*p*psi_m*i_q;
// ---- Mechanical dynamics ----
    J*der(omega_m) = T_e - T_L - B*omega_m;
    der(theta_m) = omega_m;
// ---- Inverse Park on currents (true theta_e) ----
    i_alpha = cos(theta_e)*i_d - sin(theta_e)*i_q;
    i_beta = sin(theta_e)*i_d + cos(theta_e)*i_q;
// ---- Inverse Clarke on currents (balanced 3-phase: i_a + i_b + i_c = 0) ----
    i_a = i_alpha;
    i_b = -0.5*i_alpha + (sqrt(3.0)/2.0)*i_beta;
    i_c = -0.5*i_alpha - (sqrt(3.0)/2.0)*i_beta;
    annotation(
      Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}), graphics = {Rectangle(extent = {{-100, 100}, {100, -100}}, lineColor = {0, 0, 0}, fillColor = {245, 245, 245}, fillPattern = FillPattern.Solid), Ellipse(extent = {{-50, 50}, {50, -50}}, lineColor = {0, 0, 0}, fillColor = {200, 220, 240}, fillPattern = FillPattern.Solid), Text(extent = {{-50, 92}, {50, 64}}, textString = "Slotless\nPMSM abc"), Text(extent = {{-40, 12}, {40, -12}}, textString = "abc"), Text(extent = {{-95, 90}, {-55, 70}}, textString = "v_a", horizontalAlignment = TextAlignment.Left), Text(extent = {{-95, 50}, {-55, 30}}, textString = "v_b", horizontalAlignment = TextAlignment.Left), Text(extent = {{-95, 10}, {-55, -10}}, textString = "v_c", horizontalAlignment = TextAlignment.Left), Text(extent = {{-95, -70}, {-55, -90}}, textString = "T_L", horizontalAlignment = TextAlignment.Left), Text(extent = {{55, 100}, {95, 80}}, textString = "i_a", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, 80}, {95, 60}}, textString = "i_b", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, 60}, {95, 40}}, textString = "i_c", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, 40}, {95, 20}}, textString = "omega_m", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, 20}, {95, 0}}, textString = "theta_m", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, 0}, {95, -20}}, textString = "T_e", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, -20}, {95, -40}}, textString = "i_d", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, -40}, {95, -60}}, textString = "i_q", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, -60}, {95, -80}}, textString = "v_d", horizontalAlignment = TextAlignment.Right), Text(extent = {{55, -80}, {95, -100}}, textString = "v_q", horizontalAlignment = TextAlignment.Right)}));end SlotlessPMSM_abc
  ;

end Alva;