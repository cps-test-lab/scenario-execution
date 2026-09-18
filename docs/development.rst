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

The version lives in ``package.xml`` and nowhere else: every ``setup.py`` reads its own
package's ``package.xml``, so the two cannot disagree and a release changes one file per
package. Which packages a release touches is decided by that version, too — a package at the
release version is released, one at ``0.0.0`` never is (the examples, the ``*_test``
packages, the simulation helpers, the tools, and the libraries kept out of the ROS build
farm). ``make release-list`` prints both sets. A new package goes to one or the other on
purpose, and to the release repository's ``jazzy.ignored`` if it is the latter (see below).

Changelog
---------

Each released package keeps a ``CHANGELOG.rst`` in the ROS (``catkin``) format. It is the
single source of truth for both the ROS release (consumed by ``bloom``) and the PyPI
release: the ``scenario_execution`` package ships its ``CHANGELOG.rst`` in the sdist and
links to it from PyPI via the ``Changelog`` project URL. The entries are generated from the
git history at release time — one line per commit, its subject, so write subjects that read
as changelog lines. The ``Forthcoming`` section is what the next release names.

Releasing
---------

A release goes to two places from one version: PyPI (the core ``scenario-execution``
distribution, published by CI from the tag) and the ROS build farm (the ROS packages, via
``bloom``, by hand after the tag). It is one generated pull request, one candidate tried by
hand, one tag, and bloom — four ``make`` targets, each printing the next.

1. **Prepare.** On a branch from a clean ``main``:

   .. code-block:: bash

      make release-prepare VERSION=1.6.0    # or VERSION=minor: major|minor|patch from the current

   This fills each released package's ``CHANGELOG.rst`` from the git history since the
   last tag, names that section ``1.6.0 (today)``, and sets ``<version>`` in the released
   ``package.xml`` files — and nothing else. Review the diff (the changelog entries are commit
   subjects; edit them where a subject says less than a reader needs), then commit and open
   the pull request. It needs ``catkin_pkg`` (``pip install catkin_pkg``).

2. **Try it.** Once the pull request is merged:

   .. code-block:: bash

      make release-rc VERSION=1.6.0

   This checks the commit (on ``main``, CI green, ``package.xml`` at 1.6.0, every package
   either released or in the release repository's ``jazzy.ignored``), publishes the wheel as
   ``1.6.0rcN`` to TestPyPI through the publish workflow, and lays out a **bloom rehearsal**:
   a scratch clone of the release repository pointed at a clean clone of the commit, with
   bloom and rosdep in a venv of their own. It prints two things to run by hand — a
   ``pip install`` of the candidate from TestPyPI, and one ``bloom-release --pretend`` line
   that performs the entire build-farm release and pushes nothing. Something wrong is a fix
   on ``main`` and the next candidate; nothing has been consumed.

3. **Tag.** When both hold:

   .. code-block:: bash

      make release-final VERSION=1.6.0 COMMIT=<the commit the candidate was built from>

   The same checks, plus a candidate on TestPyPI, then the two tags on that commit, both
   lightweight — bloom exports from ``jazzy-1.6.0``, and ``git describe`` must keep answering
   with the bare ``1.6.0`` (it prefers an annotated tag, and the changelog generator refuses
   one of the other shape). The push of ``1.6.0`` is what publishes to PyPI:
   ``.github/workflows/publish.yml`` builds the wheel at the version ``package.xml`` says,
   uploads it with trusted publishing, and installs it back from the index.

4. **The ROS build farm.** Printed by the previous step; with both tags on the upstream and
   ``main`` still at this version:

   .. code-block:: bash

      make ros_release ROS_DISTRO=jazzy

   ``bloom-release`` is interactive, needs a current bloom and the release repository, reads
   the version from the tip of ``main``, and opens the ``rosdistro`` pull request. It releases
   every package it finds in the upstream **except** those named in the release repository's
   ``jazzy.ignored``, and then insists the rest share one version — which is why the ``0.0.0``
   set and ``jazzy.ignored`` must agree, and why the rehearsal in step 2 exists.

Notes:

- An upload to PyPI cannot be replaced, only yanked, and ``pip`` still installs a yanked wheel
  when pinned exactly. That is why the candidate goes to TestPyPI first, and why a broken
  release is followed by the next number, never by a re-upload.
- Only a subset of the workspace is published anywhere. What is released is what carries
  the version; ``make release-list`` is the list, and it must mirror the ``release/packages``
  list for this repository in `rosdistro <https://github.com/ros/rosdistro>`_ — that list is
  what bloom produces from the non-ignored packages.
- ``catkin_prepare_release`` does not apply to this repository: it wants a literal version in
  every ``setup.py``, which is exactly the duplication that ``package.xml`` alone avoids.

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
