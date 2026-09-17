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
# Every registered RASPA test, including all six suites. HDF5's separate suite
# is not implicitly included just because it also uses BUILD_TESTING.
ctest --test-dir build/tests --output-on-failure --no-tests=error --timeout 3600 --parallel 4
cmake --install build --component app
cmake --install build --component cli
mkdir -p "$PREFIX/libexec/raspa3" "$PREFIX/share/raspa3/examples/methane-in-box"
for command in raspa3 raspa3-cli; do
  mv "$PREFIX/bin/$command" "$PREFIX/libexec/raspa3/$command"
  install -m 755 "$RECIPE_DIR/launcher.sh" "$PREFIX/bin/$command"
done
cp examples/basic/1_mc_methane_in_box/{simulation.json,force_field.json,methane.json} \
  "$PREFIX/share/raspa3/examples/methane-in-box/"
