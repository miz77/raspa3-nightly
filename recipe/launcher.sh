#!/bin/sh
set -eu
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
if [ "${RASPA_DIR+x}" != x ]; then
  RASPA_DIR=$prefix
  export RASPA_DIR
fi
exec "$prefix/libexec/raspa3/$(basename -- "$0")" "$@"
