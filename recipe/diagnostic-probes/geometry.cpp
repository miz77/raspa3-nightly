
// Temporary diagnostic probe; production sources and assertions are unchanged.
TEST(diagnostics, coincident_caps)
{
  for (double angle : {0.3, 0.5, 0.9, 1.2, 1.7, 2.5})
  {
    const SweepCircle circle = capOf(double3(0.0, 0.0, 1.0), angle);
    const double cosine = circle.cosineHalfAngle;
    const double sine = circle.sineHalfAngle;
    const double lhs = double3::dot(circle.axis, circle.axis);
    const double rhs = cosine * cosine + sine * sine;
    const bool contains = discWithinDisc(lhs, cosine, sine, cosine, sine);
    std::vector<SweepCircle> duplicate{circle, circle};
    pruneContainedDiscs(duplicate);
    const double expectedArea = 2.0 * std::numbers::pi * (1.0 + cosine);
    const double singleArea = exposedArea({circle}, 1.0);
    const double duplicateArea = exposedArea(duplicate, 1.0);
    std::println("CAP angle={:.17g} cosine={:.17g} sine={:.17g} lhs={:.17g} rhs={:.17g} residual={:.17g} contains={} survivors={} expected_area={:.17g} single_area={:.17g} duplicate_area={:.17g}",
                 angle, cosine, sine, lhs, rhs, lhs-rhs, contains, duplicate.size(),
                 expectedArea, singleArea, duplicateArea);
  }
  std::size_t failures = 0;
  for (std::size_t step = 1; step < 314; ++step)
  {
    const SweepCircle c = capOf(double3(0.0, 0.0, 1.0), double(step) / 100.0);
    if (!discWithinDisc(1.0, c.cosineHalfAngle, c.sineHalfAngle, c.cosineHalfAngle, c.sineHalfAngle)) ++failures;
  }
  std::println("CAP_SELF_CONTAINMENT failed={} total=313", failures);
}
