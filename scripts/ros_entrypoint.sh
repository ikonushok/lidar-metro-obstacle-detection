#!/bin/bash
set -e

source "/opt/ros/${ROS_DISTRO:-humble}/setup.bash"
if [ -f /app/install/setup.bash ]; then
  source /app/install/setup.bash
fi
exec "$@"
