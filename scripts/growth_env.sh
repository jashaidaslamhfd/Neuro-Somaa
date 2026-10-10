#!/usr/bin/env bash
# Growth defaults for CI / local
export YT_PRIVACY_STATUS="${YT_PRIVACY_STATUS:-public}"
export YT_SCHEDULE_PUBLISH="${YT_SCHEDULE_PUBLISH:-false}"
export GROWTH_MODE="${GROWTH_MODE:-true}"
echo "Growth env: privacy=$YT_PRIVACY_STATUS schedule=$YT_SCHEDULE_PUBLISH growth=$GROWTH_MODE"
