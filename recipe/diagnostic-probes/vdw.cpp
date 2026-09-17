
TEST(diagnostics, vdw_step_sweep)
{
  PotentialTestCase testCase{VDWParameters::Type::LennardJonesSecondOrderTaylorShifted, {119.8, 3.405}, {}};
  ForceField forceField = makeForceField(testCase, true);
  const double r = 5.0;
  const auto hessian = Potentials::potentialVDW<2>(forceField, 1.0, 1.0, r*r, 0, 0);
  const double analytic = hessian.firstDerivativeFactor + hessian.secondDerivativeFactor * r*r;
  for (double h : {1e-3, 3e-4, 1e-4, 3e-5, 2e-5, 1e-5, 3e-6, 1e-6})
  {
    const double plus = Potentials::potentialVDW<0>(forceField, 1.0, 1.0, (r+h)*(r+h), 0, 0).energy;
    const double center = Potentials::potentialVDW<0>(forceField, 1.0, 1.0, r*r, 0, 0).energy;
    const double minus = Potentials::potentialVDW<0>(forceField, 1.0, 1.0, (r-h)*(r-h), 0, 0).energy;
    const double gradientPlus = Potentials::potentialVDW<1>(forceField, 1.0, 1.0, (r+h)*(r+h), 0, 0).firstDerivativeFactor * (r+h);
    const double gradientMinus = Potentials::potentialVDW<1>(forceField, 1.0, 1.0, (r-h)*(r-h), 0, 0).firstDerivativeFactor * (r-h);
    const double energyFD = (plus-2.0*center+minus)/(h*h);
    const long double energyLD = (static_cast<long double>(plus)-2.0L*center+minus)/(static_cast<long double>(h)*h);
    const double gradientFD = (gradientPlus-gradientMinus)/(2.0*h);
    std::println("VDW h={:.17g} analytic={:.17g} energy_fd={:.17g} long_sum_fd={:.17g} gradient_fd={:.17g} ep={:.17g} ec={:.17g} em={:.17g}",
                 h, analytic, energyFD, energyLD, gradientFD, plus, center, minus);
  }
}
