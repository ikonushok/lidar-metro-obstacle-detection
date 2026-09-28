FROM ros:humble-ros-base-jammy
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libjs-three python3-numpy python3-matplotlib python3-pip python3-sklearn zstd \
    ros-humble-rosbag2-storage-default-plugins \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir lightgbm==4.5.0
WORKDIR /app
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY tests/ /app/tests/
COPY config/ /app/config/
COPY web/ /app/web/
RUN mkdir -p /app/artefacts/stage_4/cpu_viewer/vendor \
    && cp /usr/share/javascript/three/three.min.js /app/artefacts/stage_4/cpu_viewer/vendor/ \
    && cp /usr/share/javascript/three/examples/js/controls/OrbitControls.js /app/artefacts/stage_4/cpu_viewer/vendor/
RUN . /opt/ros/humble/setup.sh && colcon build --merge-install --base-paths /app/src/lidar_mosmetro3d_cpp
ENV AMENT_PREFIX_PATH=/app/install
ENV PYTHONPATH=/app/src MPLBACKEND=Agg FASTRTPS_DEFAULT_PROFILES_FILE=/app/config/fastdds.xml
CMD ["ros2", "run", "lidar_mosmetro3d_cpp", "curve_envelope_node", "--help"]
