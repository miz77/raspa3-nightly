
// Observe the failing matrix entry without changing the original test tolerance.
TEST(diagnostics, variable_cell_step_sweep)
{
  for (bool polarized : {false, true})
  {
    System system = polarized ? makePolarizableRigidMoleculePair() : makeRigidChargedPair();
    const auto cellLayout = makeCellMinimizationLayout(system.cellMinimizationType, system.monoclinicAngleType);
    const auto layout = buildMinimizationDofLayout(system.moleculeData, system.components, 0, cellLayout.size());
    const Evaluation reference = evaluate(system, layout);
    const std::size_t row = 11;
    const std::size_t column = *layout.cellDof(2);
    const double analytic = reference.hessian[row * layout.numDofs() + column];
    for (double h : {1e-3, 3e-4, 1e-4, 3e-5, 2e-5, 1e-5, 3e-6, 1e-6})
    {
      const auto displaced = [&](double rotation, double cell)
      {
        System copy = system;
        std::vector<double> displacement(layout.numDofs(), 0.0);
        displacement[row] = rotation;
        displacement[column] = cell;
        applyGeneralizedDisplacement(copy, layout, displacement);
        return evaluate(copy, layout);
      };
      const Evaluation pp = displaced(h, h);
      const Evaluation pm = displaced(h, -h);
      const Evaluation mp = displaced(-h, h);
      const Evaluation mm = displaced(-h, -h);
      const Evaluation cp = displaced(0.0, h);
      const Evaluation cm = displaced(0.0, -h);
      const Evaluation rp = displaced(h, 0.0);
      const Evaluation rm = displaced(-h, 0.0);
      const double energyFD = (pp.energy - pm.energy - mp.energy + mm.energy) / (4.0 * h * h);
      const long double energyLD = (static_cast<long double>(pp.energy) - pm.energy - mp.energy + mm.energy) /
                                   (4.0L * h * h);
      const double gradientFD = (cp.gradient[row] - cm.gradient[row]) / (2.0 * h);
      const double transposeFD = (rp.gradient[column] - rm.gradient[column]) / (2.0 * h);
      std::println("HESSIAN polarized={} row={} column={} h={:.17g} analytic={:.17g} energy_fd={:.17g} long_sum_fd={:.17g} gradient_fd={:.17g} transpose_fd={:.17g} epp={:.17g} epm={:.17g} emp={:.17g} emm={:.17g}",
                   polarized, row, column, h, analytic, energyFD, energyLD, gradientFD, transposeFD,
                   pp.energy, pm.energy, mp.energy, mm.energy);
    }
  }
}
