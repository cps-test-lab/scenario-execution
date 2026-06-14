Development
===========

Contribute
----------

Before pushing your code, please ensure that the code formatting is
correct by running:

.. code-block:: bash

   make

In case of errors you can run the autoformatter by executing:

.. code-block:: bash

   make format

Testing
-------

To run only specific tests:

.. code-block:: bash

   #using py-test
   colcon build --packages-up-to scenario_execution_ros && reset && pytest-3 -s scenario_execution_ros/test/<TEST>.py 

   #manual run
   colcon build --packages-up-to scenario_execution_ros && reset && ros2 launch scenario_execution_ros scenario_launch.py scenario:=<...> debug:=True

   #using colcon
   colcon test --packages-select scenario_execution \
      --event-handlers console_direct+ \
      --return-code-on-test-failure \
      --pytest-args -k <TEST> \
      -s

   #using colcon with filtered test
   colcon test --packages-select scenario_execution \
  --event-handlers console_direct+ \
  --return-code-on-test-failure \
  --pytest-args test/test_parameter_override.py::TestParameterOverride::test_base_params_success \
  -s

Versioning
----------

All packages share one version, kept in both ``package.xml`` and ``setup.py``. Bump it
across the whole workspace with a single command:

.. code-block:: bash

   make set_version VERSION=1.6.0    # set an explicit version
   make set_version VERSION=minor    # or bump major|minor|patch from the current version

This updates every source ``package.xml`` and ``setup.py`` (the canonical version is read
from ``scenario_execution/package.xml``). Review the diff, update the ``CHANGELOG.rst``
headings, then commit and tag, e.g. ``git commit -am 1.6.0 && git tag 1.6.0``.

Changelog
---------

Each package keeps a ``CHANGELOG.rst`` in the ROS (``catkin``) format. It is the single
source of truth for both the ROS release (consumed by ``bloom``) and the PyPI release: the
``scenario_execution`` package ships its ``CHANGELOG.rst`` in the sdist and links to it from
PyPI via the ``Changelog`` project URL, so there is no separate file to keep in sync.

Update the changelogs from the git history before tagging a release:

.. code-block:: bash

   catkin_generate_changelog --all   # fills the "Forthcoming" section of every CHANGELOG.rst
   # review/edit the entries, then set the version + date heading

Releasing
---------

A release goes to two places from the same version and changelogs: PyPI (the core
``scenario_execution`` package) and the ROS build farm (the ROS packages). The changelog
and version bump go through a pull request; tagging and publishing happen on ``main``
**after** that pull request is merged.

First, prepare the release on a branch and open a pull request:

.. code-block:: bash

   make release_tools                  # 0. one-time: install the PyPI build tooling (build + twine)

   git switch -c release-1.6.0
   make ros_changelog                  # 1. fill each CHANGELOG.rst from git history;
                                       #    then edit every "Forthcoming" -> "<version> (<date>)"
   make set_version VERSION=minor      # 2. bump version across all package.xml + setup.py
                                       #    (or VERSION=1.6.0 for an explicit version)
   make release_test                   # 3. dry run: build, validate, and upload to TestPyPI
   git commit -am "Release 1.6.0" && git push -u origin release-1.6.0   # 4. open a PR, get it reviewed + merged

Then, once the pull request is merged, tag and publish from ``main``:

.. code-block:: bash

   git switch main && git pull
   git tag 1.6.0 && git push origin 1.6.0               # 5. tag the merged release commit
   git tag jazzy-1.6.0 1.6.0 && git push origin jazzy-1.6.0   # 5b. distro tag bloom releases from

   make release                        # 6. publish to PyPI

   make ros_release ROS_DISTRO=jazzy   # 7. publish to the ROS build farm (bloom)

Notes:

- ``make release`` (and ``release_test``) first checks that the versions in
  ``scenario_execution/setup.py`` and ``scenario_execution/package.xml`` match, builds the
  sdist/wheel and validates them. Use ``make release_check`` to build and validate without
  uploading. Upload credentials are taken from twine (e.g. ``~/.pypirc`` or the
  ``TWINE_USERNAME``/``TWINE_PASSWORD`` environment variables).
- ``make ros_release`` is interactive, needs a configured release repository, and opens a
  ``rosdistro`` pull request. It takes the rosdistro *repository* key (``ROS_REPO``,
  default ``scenario_execution``), not individual package names; ``ROS_DISTRO`` defaults to
  ``jazzy``.
- bloom exports the upstream sources from a distro-prefixed ``<distro>-<version>`` tag
  (e.g. ``jazzy-1.6.0``), **not** the bare ``<version>`` tag. Both must exist on the upstream
  repository before running ``make ros_release`` — if the distro tag is missing,
  ``bloom-export-upstream`` fails with ``'<distro>-<version>' is not a tag in the upstream
  repository`` and no tarball is created. Step 5b above creates it alongside the bare tag.
- Only a subset of the workspace is published to ROS; the rest (examples, ``*_test``
  packages, simulation helpers, and the docker/kubernetes/moveit2/pybullet/floorplan_dsl
  libraries) are intentionally **not** released. The released set is listed in
  ``ROS_RELEASE_PACKAGES`` in the ``Makefile`` and must mirror the ``release/packages`` list
  for this repository in `rosdistro <https://github.com/ros/rosdistro>`_. Run
  ``make ros_release_packages`` to print the released vs. disabled split before opening a
  rosdistro pull request, and keep the disabled packages out of that list.

Developing and Debugging with Visual Studio Code
------------------------------------------------

To prevent certain issues, please use the following command for building (remove `/build` and `/install`` if another command was used before).

.. code-block:: bash

   colcon build --symlink-install


In VSCode create new debugging configuration file: Run -> "Add Configuration..."

Add the following entry to the "configurations" element within the previously created `launch.json` file (replace the arguments as required):


.. code-block:: json

           {
               "name": "scenario_execution_ros",
               "type": "python",
               "request": "launch",
               "program": "./install/scenario_execution_ros/lib/scenario_execution_ros/scenario_execution_ros",
               "console": "integratedTerminal",
               "cwd": "${workspaceFolder}",
               "args": ["-l", "TEST_SCENARIO.osc"],
           }

Create an `.env` file by executing:

.. code-block:: bash

   source /opt/ros/humble/setup.bash
   source install/setup.bash
   echo PYTHONPATH=$PYTHONPATH > .env
   echo HOME=$HOME >> .env
   echo AMENT_PREFIX_PATH=$AMENT_PREFIX_PATH >> .env
   echo LD_LIBRARY_PATH=$LD_LIBRARY_PATH >> .env


In vscode, open user settings and enable the following settings:

.. code-block::

   "python.terminal.activateEnvInCurrentTerminal": true


To execute the debug configuration either switch to debug view (on the left) and click on "play" or press F5.


Best known Methods
------------------

Implement an Action
^^^^^^^^^^^^^^^^^^^

- If an action's ``setup()`` fails, raise an exception
- Use a state machine, if multiple steps are required
- Implement a ``shutdown()`` method to cleanup on scenario end.
- For debugging/logging:
   - Make use of ``self.feedback_message``
   - Make use of ``kwargs['logger']``, available in ``setup()``
   - If you want to draw markers for RViz, use ``kwargs['marker_handler']``, available in ``setup()`` (with ROS backend)
- Use arguments from ``__init__()`` for a longer running initialization in ``setup()`` and the arguments from ``execute()`` to set values just before executing the action.
- ``__init__()`` and ``setup()`` are called once, ``execute()`` might be called multiple times.
- osc2 arguments can only be consumed once, either in ``__init__()`` or ``execute()``. Exception: If an ``associated_actor`` exists, it's an argument of both methods.
- Arguments that need late resolving (e.g. referring to variables or external methods) need to be consumed in ``execute()``.
- ``setup()`` provides several arguments that might be useful:
  - ``input_dir``: Directory containing the scenario file
  - ``output_dir``: If given on command-line, contains the directory to save output to
  - ``node``: (``scenario_execution_ros`` only): ROS node to utilize (e.g. create subscribers)
- If your action makes use of variables, set ``resolve_variable_reference_arguments_in_execute`` in ``BaseAction.__init()`` to  ``False``.
  The ``execute()`` method arguments will then contain resolved values as before, except for variable arguments which are accessible
  as ``VariableReference`` (with methods ``set_value()`` and ``get_value()``).

Implement an Action with Complex Behavior Tree
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For actions that need to provide their own complex behavior tree implementation, inherit from ``BaseActionSubtree`` instead of ``BaseAction``:

- Override ``create_subtree()`` method instead of ``update()``
- ``create_subtree()`` should return a complete ``py_trees.behaviour.Behaviour`` that implements the action logic
- All OSC2 parameters are passed to ``create_subtree()`` method, similar to ``execute()`` in ``BaseAction``
- The subtree is created once during action initialization and managed internally
- Use ``BaseActionSubtree`` when you need composite behaviors, decorators, or complex state machines that are better expressed as behavior trees rather than a single behavior's ``update()`` method
- Arguments follow the same rules as ``BaseAction``: can be consumed in ``__init__()`` or ``create_subtree()``, but not both
