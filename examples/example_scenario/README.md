# Example Scenario

To run the Example Scenario, first build the `scenario_execution` package:

```bash
colcon build --packages-up-to scenario_execution
```

Source the workspace:

```bash
source install/setup.bash
```

Now, run the following command to launch the scenario:

```bash
ros2 run scenario_execution scenario_execution examples/example_scenario/hello_world.osc
```

`held_for_duration.osc` shows how to wait until a condition has held for a duration, restarting
the timer whenever the condition breaks:

```bash
ros2 run scenario_execution scenario_execution examples/example_scenario/held_for_duration.osc
```

For a more detailed understanding of the code structure and scenario implementation please refer to the [tutorial documentation](https://cps-test-lab.github.io/scenario-execution/tutorials.html).
