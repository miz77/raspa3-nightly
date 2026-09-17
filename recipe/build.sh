#!/usr/bin/env bash
set -euo pipefail
cd "$SRC_DIR/raspa3"
"$BUILD_PREFIX/bin/python" - <<'PY'
import os
from pathlib import Path
import re

version = re.search(r"project\(raspa3\s+VERSION\s+(\S+)", Path("CMakeLists.txt").read_text())[1]
assert version == os.environ["NIGHTLY_VERSION"], (version, os.environ["NIGHTLY_VERSION"])
PY
export CLANG="$CC" CLANGXX="$CXX"
# Platform variables are provided by rattler-build.
: "${target_platform:?}" "${build_platform:?}"
extra=()
case "$target_platform" in
  osx-arm64)
    preset=mac_conda_raspa3
    SDKROOT="$(xcrun --sdk "$NIGHTLY_MACOS_SDK" --show-sdk-path)"
    export SDKROOT
    export CONDA_BUILD_SYSROOT="$SDKROOT"
    extra+=(-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 "-DCMAKE_OSX_SYSROOT=$SDKROOT")
    library_suffix=dylib
    ;;
  linux-64)
    preset=linux_conda_raspa3
    library_suffix=so
    ;;
  *)
    echo "Only native osx-arm64 and linux-64 are supported" >&2
    exit 1
    ;;
esac
test "$build_platform" = "$target_platform"
cmake --version
"$CXX" --version
"$BUILD_PREFIX/bin/clang-scan-deps" --version
# Diagnostic branch only: keep the source and all other flags identical.
"$BUILD_PREFIX/bin/python" - <<'PYFLAGS'
import json
import os
from pathlib import Path

path = Path("CMakePresets.json")
presets = json.loads(path.read_text())
preset = next(p for p in presets["configurePresets"] if p["name"] == "linux_conda_raspa3")
flags = preset["cacheVariables"]["CMAKE_CXX_FLAGS_RELEASE"]
mode = os.environ["NIGHTLY_DIAGNOSTIC_MODE"]
assert mode in ("fast", "strict")
if mode == "strict":
    assert "-ffast-math" in flags
    preset["cacheVariables"]["CMAKE_CXX_FLAGS_RELEASE"] = flags.replace("-ffast-math", "-fno-fast-math")
print("Diagnostic mode:", mode)
print("CMAKE_CXX_FLAGS_RELEASE:", preset["cacheVariables"]["CMAKE_CXX_FLAGS_RELEASE"])
path.write_text(json.dumps(presets, indent=2) + "\n")
PYFLAGS
cmake -B build --preset="$preset" "${extra[@]}" \
  "-DCMAKE_BUILD_RPATH=$PREFIX/lib" "-DCMAKE_INSTALL_RPATH=$PREFIX/lib" \
  -DCMAKE_FIND_FRAMEWORK=LAST -DBLA_VENDOR=Generic \
  "-DBLAS_LIBRARIES=$PREFIX/lib/libblas.$library_suffix" \
  "-DLAPACK_LIBRARIES=$PREFIX/lib/liblapack.$library_suffix" \
  "-DOpenCL_LIBRARY=$PREFIX/lib/libOpenCL.$library_suffix" \
  "-DOpenCL_INCLUDE_DIR=$PREFIX/include" \
  -DFETCHCONTENT_SOURCE_DIR_HDF5="$SRC_DIR/hdf5" \
  -DFETCHCONTENT_SOURCE_DIR_GOOGLETEST="$SRC_DIR/googletest" \
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
  -DHDF5_ALLOW_EXTERNAL_SUPPORT=NO \
  -DBUILD_APP=ON -DBUILD_CLI=ON -DBUILD_TESTING=ON \
  -DBUILD_PYTHON=OFF -DBUILD_MAC_PACKAGE=OFF -DBUILD_DOXYGEN=OFF -DBUILD_BENCHMARKS=OFF
cmake --build build --parallel 4
# Diagnostic subset only; this is not a replacement for full validation.
mkdir -p diagnostics
cp build/CMakeCache.txt CMakePresets.json diagnostics/
"$BUILD_PREFIX/bin/python" - <<'PYSELECT'
import json
import subprocess
from pathlib import Path

names = {
    "exact_sphere_sweep.pruning_keeps_one_of_a_pair_of_equals_and_the_order_of_the_rest",
    "thermobarostat.initialization_recomputes_mass_after_dof_constraint",
    "hybrid_mc.flexible_framework_only_does_not_throw_and_restores_on_reject",
    "minimization_variable_cell.rigid_charged_mixed_blocks_match_finite_difference",
    "minimization_variable_cell.polarization_rigid_molecule_real_space_matches_finite_difference",
    "vdw_potentials.second_order_taylor_shifted_spatial_derivatives_match_finite_difference",
    "MC_SEMI_FLEXIBLE_CBMC.pentane_muvt_geometry_molecular_dynamics",
    "MC_SEMI_FLEXIBLE_CBMC.pentane_mupt_geometry_molecular_dynamics",
}
names = {name + ".noArgs" for name in names}
result = subprocess.run(["ctest", "--test-dir", "build/tests", "--show-only=json-v1"], check=True, capture_output=True, text=True)
registered = {test["name"] for test in json.loads(result.stdout)["tests"]}
assert names <= registered, names - registered
Path("diagnostics/selected-tests.txt").write_text("\n".join(sorted(names)) + "\n")
Path("diagnostics/registered-tests.json").write_text(result.stdout)
PYSELECT
status=0
for round in 1 2 3; do
  ctest --test-dir build/tests --tests-from-file "$PWD/diagnostics/selected-tests.txt" \
    --output-on-failure --no-tests=error --timeout 600 --parallel 4 \
    --output-junit "$PWD/diagnostics/round-$round.xml" 2>&1 | tee "diagnostics/round-$round.log" || status=1
  cp build/tests/Testing/Temporary/LastTest.log "diagnostics/LastTest-$round.log"
done
printf '%s\n' "$status" >diagnostics/test-exit-status.txt
# Preserve an honest failure, without bypassing any production gate.
if ((status != 0)); then
  exit "$status"
fi
cmake --install build --component app
cmake --install build --component cli
mkdir -p "$PREFIX/libexec/raspa3" "$PREFIX/share/raspa3/examples/methane-in-box"
for command in raspa3 raspa3-cli; do
  mv "$PREFIX/bin/$command" "$PREFIX/libexec/raspa3/$command"
  install -m 755 "$RECIPE_DIR/launcher.sh" "$PREFIX/bin/$command"
done
cp examples/basic/1_mc_methane_in_box/{simulation.json,force_field.json,methane.json} \
  "$PREFIX/share/raspa3/examples/methane-in-box/"
