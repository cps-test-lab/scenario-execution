cmake_minimum_required(VERSION 3.5)
project(scenario_execution_rviz)

set(CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 14)

add_compile_options(-Wall -Wextra -Werror -flto -fvisibility=hidden -z noexecstac -fPIC -Wl,-z,relro,-z,now -fstack-protector-strong)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rviz_common REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(scenario_execution_interfaces REQUIRED)
find_package(py_trees_ros_interfaces REQUIRED)
find_package(tf2 REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rviz_ogre_vendor REQUIRED)

set(CMAKE_AUTOMOC ON)

# Lyrical (Ubuntu 26.04) ships rviz built against Qt6.
find_package(Qt6 REQUIRED COMPONENTS Core Widgets)
set(QT_LIBRARIES Qt6::Widgets)

set(SRC_FILES src/indicator_widget.cpp
              src/control_panel.cpp
              src/scenario_view.cpp)

qt6_add_resources(SRC_FILES scenario_execution_rviz.qrc)

add_library(${PROJECT_NAME} SHARED ${SRC_FILES})

# ament_target_dependencies was removed in Lyrical; link the modern CMake targets directly.
target_link_libraries(${PROJECT_NAME} ${QT_LIBRARIES}
                      rviz_ogre_vendor::OgreMain
                      rclcpp::rclcpp
                      rviz_common::rviz_common
                      ${nav_msgs_TARGETS}
                      ${std_srvs_TARGETS}
                      ${scenario_execution_interfaces_TARGETS}
                      ${py_trees_ros_interfaces_TARGETS}
                      tf2::tf2)

target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_14)

pluginlib_export_plugin_description_file(rviz_common
                                          plugin_description.xml)

ament_export_libraries(${PROJECT_NAME})

install(
  TARGETS ${PROJECT_NAME}
  EXPORT ${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

install(FILES plugin_description.xml DESTINATION "share/${PROJECT_NAME}")

install(DIRECTORY icons/ DESTINATION "share/${PROJECT_NAME}")

ament_package()

