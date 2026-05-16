model SlotlessPMSM_dq "Surface-PM slotless PMSM in dq frame (Ld = Lq = Ls). No abc-frame boundary; vd, vq, TL go in directly."
  // ---------- Electrical parameters ----------
  parameter Real Rs(unit = "Ohm") = 0.5 "Phase resistance";
  parameter Real Ls(unit = "H") = 100e-6 "Synchronous inductance (Ld = Lq for slotless surface-PM)";
  parameter Real lambdaPM(unit = "Wb") = 0.02 "Permanent magnet flux linkage";
  parameter Integer p = 4 "Pole pairs";
  // ---------- Mechanical parameters ----------
  parameter Real J(unit = "kg.m2") = 1e-4 "Rotor inertia";
  parameter Real B(unit = "N.m.s/rad") = 1e-5 "Viscous friction coefficient";
  // ---------- Initial conditions ----------
  parameter Real id0(unit = "A") = 0.0 "Initial d-axis current";
  parameter Real iq0(unit = "A") = 0.0 "Initial q-axis current";
  parameter Real omega_m0(unit = "rad/s") = 0.0 "Initial mechanical speed";
  parameter Real theta_m0(unit = "rad") = 0.0 "Initial mechanical angle";
  // ---------- Inputs ----------
  Modelica.Blocks.Interfaces.RealInput vd(unit = "V") "d-axis stator voltage" annotation(
    Placement(transformation(extent = {{-140, 60}, {-100, 100}})));
  Modelica.Blocks.Interfaces.RealInput vq(unit = "V") "q-axis stator voltage" annotation(
    Placement(transformation(extent = {{-140, 0}, {-100, 40}})));
  Modelica.Blocks.Interfaces.RealInput TL(unit = "N.m") "Load torque (positive opposes motion)" annotation(
    Placement(transformation(extent = {{-140, -100}, {-100, -60}})));
  // ---------- Outputs ----------
  Modelica.Blocks.Interfaces.RealOutput id(unit = "A", start = id0) "d-axis stator current" annotation(
    Placement(transformation(extent = {{100, 70}, {120, 90}})));
  Modelica.Blocks.Interfaces.RealOutput iq(unit = "A", start = iq0) "q-axis stator current" annotation(
    Placement(transformation(extent = {{100, 30}, {120, 50}})));
  Modelica.Blocks.Interfaces.RealOutput omega_m(unit = "rad/s", start = omega_m0) "Mechanical angular speed" annotation(
    Placement(transformation(extent = {{100, -10}, {120, 10}})));
  Modelica.Blocks.Interfaces.RealOutput theta_m(unit = "rad", start = theta_m0) "Mechanical rotor angle" annotation(
    Placement(transformation(extent = {{100, -50}, {120, -30}})));
  Modelica.Blocks.Interfaces.RealOutput Te(unit = "N.m") "Electromagnetic torque" annotation(
    Placement(transformation(extent = {{100, -90}, {120, -70}})));
protected
  Real omega_e(unit = "rad/s") "Electrical angular speed (= p * omega_m)";
  Real theta_e(unit = "rad") "Electrical angle (= p * theta_m)";
initial equation
  id = id0;
  iq = iq0;
  omega_m = omega_m0;
  theta_m = theta_m0;
equation
  // Angle propagation.
  omega_e = p * omega_m;
  theta_e = p * theta_m;
  // dq stator voltage equations (Ld = Lq = Ls).
  vd = Rs*id + Ls*der(id) - omega_e*Ls*iq;
  vq = Rs*iq + Ls*der(iq) + omega_e*Ls*id + omega_e*lambdaPM;
  // Electromagnetic torque for non-salient (Ld = Lq) machine.
  Te = 1.5 * p * lambdaPM * iq;
  // Mechanical dynamics.
  J*der(omega_m) = Te - TL - B*omega_m;
  der(theta_m) = omega_m;
  annotation(
    Icon(coordinateSystem(extent = {{-100, -100}, {100, 100}}), graphics = {
      Rectangle(extent = {{-100, 100}, {100, -100}}, lineColor = {0, 0, 0}, fillColor = {245, 245, 245}, fillPattern = FillPattern.Solid),
      Ellipse(extent = {{-50, 50}, {50, -50}}, lineColor = {0, 0, 0}, fillColor = {200, 220, 240}, fillPattern = FillPattern.Solid),
      Text(extent = {{-50, 92}, {50, 64}}, textString = "Slotless\nPMSM dq"),
      Text(extent = {{-40, 12}, {40, -12}}, textString = "dq"),
      Text(extent = {{-95, 90},  {-55, 70}},  textString = "vd",      horizontalAlignment = TextAlignment.Left),
      Text(extent = {{-95, 30},  {-55, 10}},  textString = "vq",      horizontalAlignment = TextAlignment.Left),
      Text(extent = {{-95, -70}, {-55, -90}}, textString = "TL",      horizontalAlignment = TextAlignment.Left),
      Text(extent = {{55, 90},   {95, 70}},   textString = "id",      horizontalAlignment = TextAlignment.Right),
      Text(extent = {{55, 50},   {95, 30}},   textString = "iq",      horizontalAlignment = TextAlignment.Right),
      Text(extent = {{55, 10},   {95, -10}},  textString = "omega_m", horizontalAlignment = TextAlignment.Right),
      Text(extent = {{55, -30},  {95, -50}},  textString = "theta_m", horizontalAlignment = TextAlignment.Right),
      Text(extent = {{55, -70},  {95, -90}},  textString = "Te",      horizontalAlignment = TextAlignment.Right)}));
end SlotlessPMSM_dq;
