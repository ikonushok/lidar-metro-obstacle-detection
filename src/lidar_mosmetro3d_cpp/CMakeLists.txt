cmake_minimum_required(VERSION 3.16)
project(lidar_mosmetro3d_cpp)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

set(CURVE_ENVELOPE_SOURCES
  ../cpp/curve_envelope_core.cpp
  ../cpp/auto_rails_core.cpp
  ../cpp/cuda_envelope_stub.cpp
  src/curve_envelope_node.cpp)

add_executable(curve_envelope_node
  ${CURVE_ENVELOPE_SOURCES})
target_compile_features(curve_envelope_node PRIVATE cxx_std_17)
target_include_directories(curve_envelope_node PRIVATE ../cpp)
ament_target_dependencies(curve_envelope_node rclcpp sensor_msgs std_msgs)
install(TARGETS curve_envelope_node DESTINATION lib/${PROJECT_NAME})

add_executable(curve_pipeline_stream_cli
  ../cpp/curve_pipeline_stream_cli.cpp
  ../cpp/auto_rails_core.cpp
  ../cpp/curve_envelope_core.cpp)
target_compile_features(curve_pipeline_stream_cli PRIVATE cxx_std_17)
target_include_directories(curve_pipeline_stream_cli PRIVATE ../cpp)
install(TARGETS curve_pipeline_stream_cli DESTINATION lib/${PROJECT_NAME})

ament_package()
