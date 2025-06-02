# Example Test Publisher

Test the functionality of `examples_rclpy_minimal_publisher`with `scenario_execution`.


```bash
sudo apt install ros-jazzy-examples-rclpy-minimal-publisher
colcon build --packages-up-to scenario_execution
```

Source the workspace:

```bash
source install/setup.bash
```

Now, run the following command to launch the scenario:

```bash
ros2 run scenario_execution scenario_execution examples/example_test_publisher/test_publisher.osc
```
