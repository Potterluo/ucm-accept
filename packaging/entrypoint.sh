#!/bin/sh
set -eu

CONFIG="${UCM_CONFIG:-/etc/ucm-accept/config.yaml}"
OUTPUTS="${UCM_OUTPUTS:-/data/outputs}"

exec ucm-accept --config "$CONFIG" --outputs "$OUTPUTS" "$@"
