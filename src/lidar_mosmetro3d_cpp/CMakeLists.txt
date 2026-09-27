cmake_minimum_required(VERSION 3.16)
project(lidar_mosmetro3d_cpp)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

option(LIDAR_ENABLE_CUDA "Build the optional CUDA envelope backend" OFF)

set(CURVE_ENVELOPE_SOURCES
  ../cpp/curve_envelope_core.cpp
  ../cpp/auto_rails_core.cpp
  src/curve_envelope_node.cpp)

if(LIDAR_ENABLE_CUDA)
  enable_language(CUDA)
  find_package(CUDAToolkit REQUIRED)
  list(APPEND CURVE_ENVELOPE_SOURCES ../cpp/cuda_envelope.cu)
else()
  list(APPEND CURVE_ENVELOPE_SOURCES ../cpp/cuda_envelope_stub.cpp)
endif()

add_executable(curve_envelope_node
  ${CURVE_ENVELOPE_SOURCES})
target_compile_features(curve_envelope_node PRIVATE cxx_std_17)
target_include_directories(curve_envelope_node PRIVATE ../cpp)
ament_target_dependencies(curve_envelope_node rclcpp sensor_msgs std_msgs)
if(LIDAR_ENABLE_CUDA)
  # The target stand has Ada SM 89. PTX is JIT-compatible with newer NVIDIA GPUs.
  set_target_properties(curve_envelope_node PROPERTIES CUDA_STANDARD 17 CUDA_STANDARD_REQUIRED ON CUDA_ARCHITECTURES "89-virtual")
  # ament_target_dependencies uses CMake's plain signature for this target.
  target_link_libraries(curve_envelope_node CUDA::cudart)
endif()
install(TARGETS curve_envelope_node DESTINATION lib/${PROJECT_NAME})

add_executable(curve_pipeline_stream_cli
  ../cpp/curve_pipeline_stream_cli.cpp
  ../cpp/auto_rails_core.cpp
  ../cpp/curve_envelope_core.cpp)
target_compile_features(curve_pipeline_stream_cli PRIVATE cxx_std_17)
target_include_directories(curve_pipeline_stream_cli PRIVATE ../cpp)
install(TARGETS curve_pipeline_stream_cli DESTINATION lib/${PROJECT_NAME})

ament_package()
