^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package scenario_execution_nav2
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1.7.0 (2026-09-21)
------------------
* The nav2 actions work with navigation2 1.3 (Jazzy) and 1.5 (Lyrical): ``nav_through_poses`` and ``follow_waypoints`` send the goal message each version defines, and ``init_nav2`` uses the stock ``BasicNavigator`` (`#116 <https://github.com/cps-test-lab/scenario-execution/issues/116>`_)
* ``init_nav2`` publishes the initial pose again, every 2 s, while the transform to the robot is missing, instead of waiting without end when the first one was lost (`#116 <https://github.com/cps-test-lab/scenario-execution/issues/116>`_)
* Contributors: fred-labs

1.6.0 (2026-09-18)
------------------
* Measure a scenario's durations on simulated time under use_sim_time (`#104 <https://github.com/cps-test-lab/scenario-execution/issues/104>`_)
* Contributors: fred-labs

1.5.0 (2026-06-14)
------------------
* Follow waypoints (`#62 <https://github.com/cps-test-lab/scenario-execution/issues/62>`_)
* Support adding modifiers (`#60 <https://github.com/cps-test-lab/scenario-execution/issues/60>`_)
* Added follow_waypoints nav2 action (`#61 <https://github.com/cps-test-lab/scenario-execution/issues/61>`_)
* Contributors: Samuel Wiest, Frederik Pasch

1.4.0 (2025-11-27)
------------------

1.3.0 (2025-06-04)
------------------
* example_nav2: use loopback navigation

1.2.1 (2025-05-27)
------------------
* update py-trees dependency
* update from OpenSCENARIO 2.0 to OpenSCENARIO DSL V2.1.0

1.2.0 (2024-10-02)
------------------
* Initial creation of nav2 library for scenario execution
