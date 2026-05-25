#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ORB_INSTANCE_ENV="${ROOT}/.orb-instance.env"
exec "${ROOT}/scripts/launch_orb_instance.sh"
