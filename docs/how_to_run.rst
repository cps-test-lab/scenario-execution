How to run
==========

.. _runtime_parameters:

Runtime Parameters
------------------

.. list-table:: 
   :header-rows: 1
   :class: tight-table   
   
   * - Parameter
     - Description
   * - ``-h`` ``--help``
     - show help message
   * - ``-d`` ``--debug``
     - (For debugging) print internal debugging output
   * - ``--dot``
     - Write dot files of resulting py-tree (``<scenario-name>.[dot|png|svg]``). Writes files into current directory if no ``output-dir`` is given.
   * - ``-l`` ``--log-model``
     - (For debugging) Produce tree output of parsed scenario
   * - ``-n`` ``--dry-run``
     - Parse and resolve scenario, but do not execute
   * - ``-o OUTPUT_DIR`` ``--output-dir OUTPUT_DIR``
     - Directory for output (e.g. test results)
   * - ``--scenario-parameter-file YAML_FILE``
     - Parameter definition used to override default scenario parameter definitions. See `Override scenario parameters`_ for details.
   * - ``--create-scenario-parameter-file-template``
     - Create a template yaml file for overriding scenario parameters. The file will be named like specified by ``--scenario-parameter-file``.
   * - ``-t`` ``--live-tree``
     - (For debugging) Show current state of py tree
   * - ``--post-run POST_RUN_COMMAND``
     - Command or script to run after scenario execution. The command will be called as ``<command> <output_dir>``. Can be specified multiple times; commands are executed in order with a timeout of 10 minutes each. Failures are logged but do not stop subsequent commands. Example: ``--post-run ./post.sh --post-run ./cleanup.sh``
   * - ``--simulation MODULE:CLASS``
     - Step-based simulation interface to use. The value must be in ``module.path:ClassName`` format, where the class implements :class:`SimulationInterface <scenario_execution.SimulationInterface>` and is instantiated with no arguments. See `Step-based simulation`_ for details.
   * - ``--snapshot-period SNAPSHOT_PERIOD``
     - How often (in seconds) to publish behavior tree snapshots to ``/scenario_execution/snapshots``. Default: only on status change. Set to a float value (e.g. ``--snapshot-period 1.0`` for every second).

Run locally with ROS2
---------------------

First, build the packages:

.. code-block:: bash

   colcon build --packages-up-to scenario_execution_gazebo
   source install/setup.bash

To run an osc-file with ROS2:

.. code-block:: bash

   ros2 run scenario_execution_ros scenario_execution_ros $(PATH_TO_SCENARIO_FILE)

To log the current state of the behavior tree during execution, add the ``-t`` flag as an argument and run it again:

.. code-block:: bash

   ros2 run scenario_execution_ros scenario_execution_ros $(PATH_TO_SCENARIO_FILE) -t

Additional parameters are describe in section :ref:`runtime_parameters`.

Run as standalone Python package without ROS2
---------------------------------------------

After installing :repo_link:`scenario_execution` using pip (see :ref:`install_with_pip`), you can execute a scenario with the following command

.. code-block:: bash

   scenario_execution $(PATH_TO_SCENARIO_FILE)

To log the current state of the behavior tree during execution, add the ``-t`` flag as an argument and run it again:

.. code-block:: bash

   scenario_execution $(PATH_TO_SCENARIO_FILE) -t

Additional parameters are describe in section :ref:`runtime_parameters`.



Run with Development Container inside Visual Studio Code
--------------------------------------------------------

Prerequisites
^^^^^^^^^^^^^

If not already installed, install the docker engine on your system according to the `installation instructions <https://docs.docker.com/engine/install/>`_ or, if you need GPU support, follow the `nvidia installation instructions <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html>`_.

Make sure you follow the `post installation steps <https://docs.docker.com/engine/install/linux-postinstall/>`_.

To make sure, that the docker daemon is properly set up, run

.. code-block:: bash

   docker run hello-world

Make sure you have installed the necessary `Visual Studio Code <https://code.visualstudio.com/>`_ extensions, namely the `docker extension <https://code.visualstudio.com/docs/containers/overview>`_ as well as the `Dev Container <https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers>`_ extension.

Open Scenario Execution in Development Container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

First, build the packages:

.. code-block:: bash

   colcon build

Now, open the root folder of the `scenario execution repository <https://github.com/cps-test-lab/scenario-execution>`_ in Visual Studio Code by running 

.. code-block:: bash

   code /path/to/scenario_execution

in a terminal.
Make sure, that your ``ROS_DOMAIN_ID`` is properly set in the terminal you start Visual Studio Code from.
Then, click the blue item in the lower left corner

.. figure:: images/vscode1.png
   :alt: Visual Studio Code item


Afterwards, select "Reopen in Container " in the Selection Window inside Visual Studio Code

.. figure:: images/vscode2.png
   :alt: Visual Studio Code Reopen in Container

Now Visual Studio Code should build the development container and open your current working directory inside the container after it successfully built the image.
If you now open a terminal inside Visual Studio Code, you can run and test your development safely inside the development container by running any of the :repo_link:`examples` (see :ref:`tutorials` for further details).

Once you are done, you can cancel the remote connection, by again clicking on the blue item in the lower left corner and select "Close Remote Connection"

.. figure:: images/vscode3.png
   :alt: Visual Studio Code cancel remote connection

Visualize Scenario with PyTrees ROS Viewer
------------------------------------------

Before getting started, ensure that the PyQt5 version 5.14 Python library is installed. You can check PyQt5 version using the following command:

.. code-block:: bash

   pip freeze | grep -i pyqt

If any PyQt5 libraries are detected, it's recommended to uninstall them to avoid conflicts:

.. code-block:: bash

   pip3 uninstall PyQt5 PyQt5-Qt5 PyQt5-sip PyQtWebEngine PyQtWebEngine-Qt5

Additionally, if the default PyQtWebEngine is present, remove it using:

.. code-block:: bash

   sudo apt remove python3-pyqt5.qtwebengine

Next, install PyQt and PyQtWebEngine version 5.14:

.. code-block:: bash

   pip install PyQt5==5.14
   pip install PyQtWebEngine==5.14

Once PyQt is set up, clone the ``py_trees_ros_viewer`` repository:

.. code-block:: bash

   git clone git@github.com:splintered-reality/py_trees_ros_viewer.git

After cloning, build the package using ``colcon build`` and source the workspace.

Now, to open the viewer, execute the following command:

.. code-block:: bash

   py-trees-tree-viewer --no-sandbox

Finally, in a separate terminal, run the scenario file to visualize the behavior tree.

Example:

.. code-block:: bash

      ros2 run scenario_execution_ros scenario_execution_ros =examples/example_scenario/hello_world.osc

.. figure:: images/py_tree_viewer.png
   :alt: Behavior Tree Viewer 


Please note that this method has been tested on Ubuntu 22.04. If you are using any other distribution, please ensure that 
PyQtEngine works on your machine and render web pages correctly.

Scenario Coverage
-----------------
The ``scenario_execution_coverage`` package provides the ability to run variations of a scenario from a single scenario definition. It offers a fast and efficient method to test scenario with different attribute values, streamlining the development and testing process.

Below are the steps to run a scenario using ``scenario_execution_coverage``..

First, build the packages:

.. code-block:: bash

   colcon build --packages-up-to scenario_execution_coverage
   source install/setup.bash

Then, generate the scenario files for each variation of scenario  using the ``scenario_variation`` executable, you can pass your own custom scenario as an input. For this exercise, we will use a scenario present in  :repo_link:`examples/example_scenario_variation/`.

.. code-block:: bash

   scenario_variation examples/example_scenario_variation/example_scenario_variation.osc

This will save scenario variation files with the ``.sce`` extension in the ``out`` folder within the current working directory.

To execute the generated scenario variations, run the ``scenario_batch_execution`` executable. This command will process all scenarios files present in the ``out`` folder and execute them sequentially.

.. code-block:: bash

   scenario_batch_execution -i out -o scenario_output -- ros2 run scenario_execution_ros scenario_execution_ros {SCENARIO} --output-dir {OUTPUT_DIR}

above command requires three arguments.

    - ``-i``: directory where the scenario files ``.sce`` are stored
    - ``-o``: directory where the output ``log`` and ``xml`` files will be saved (for each scenario file within a separate folder)
    - ``-- ros2 run scenario_execution_ros scenario_execution_ros {SCENARIO} --output-dir {OUTPUT_DIR}``: launch command to launch scenarios

.. note::
   ``scenario_batch_execution`` can be used for any scenario-files, not only those generated by ``scenario_variation``.

The return code of ``scenario_batch_execution`` is ``0`` if all tested scenarios succeeded. The output can be found within the specified output-folder:
 
.. code-block:: bash

   <output_folder>/
      text.xml        # overall test result (summary of all tested scenarios)
      <scenario1>/    # directory for scenario
         test.xml     # test result of scenario
         log.txt      # log output of scenario execution
         ...          # other files generated by scenario execution run (e.g. rosbag)

         
.. note::
   ``scenario_batch_execution`` creates a junit xml compatible file that can easily be integrated into a CI pipeline. An example can be found here: :repo_link:`.github/workflows/test_build.yml`

.. _override_scenario_parameters:

Override scenario parameters
----------------------------

To override scenario parameters, specify the required parameters within a yaml file and use the command-line parameter ``--scenario-parameter-file``.

Let's look at the following example scenario ``my_scenario.osc`` with the parameter ``my_base_param`` and ``my_struct_param``. 

.. code-block::

    import osc.helpers

    scenario my_scenario:
        my_base_param: string = "default value"
        my_struct_param: position_3d
        do serial:
            log(my_base_param)
            log(my_struct_param)

To override the parameter, the following yaml file ``overrides.yaml`` can be used.

.. code-block:: yaml

   my_scenario:
     my_base_param: "my_val"
     my_struct_param:
       x: 1.0
       y: 2.0
       z: 0.0

The following command executes the scenario with the defined override.

.. code-block:: bash

   ros2 run scenario_execution_ros scenario_execution_ros --scenario-parameter-file overrides.yaml my_scenario.osc 

If physical literals get overridden, the values are expected in SI base units: For example specify value in meter (e.g. ``42.0``) for ``length``; specify value in seconds for ``time``.

An initial override template file can be created using the command-line parameter ``--create-scenario-parameter-file-template``. This will create a yaml file named by ``--scenario-parameter-file`` in the current working directory.

.. _step_based_simulation:

Step-based simulation
---------------------

Scenario Execution supports running scenarios against step-based simulators (e.g. MuJoCo, PyBullet, custom hardware-in-the-loop) without any ROS dependency.

In step-based mode the framework drives the loop: it calls ``simulation.step()`` once per behavior-tree tick, advances a :class:`SimulationClock <scenario_execution.SimulationClock>`, and then ticks the behavior tree. There is no ``time.sleep()`` — the scenario runs as fast as the simulator allows.

**Implementing a SimulationInterface**

Create a class that inherits from :class:`SimulationInterface <scenario_execution.SimulationInterface>` and implement its abstract methods:

.. code-block:: python

   # my_pkg/my_sim.py
   from scenario_execution import SimulationInterface

   class MySimulation(SimulationInterface):

       @property
       def dt(self) -> float:
           """Duration of one simulation step in seconds."""
           return 0.002  # 500 Hz

       def setup(self, **kwargs) -> None:
           """Called once before any scenario runs. Load worlds, connect to
           simulator processes, allocate resources here."""
           import mujoco
           self._model = mujoco.MjModel.from_xml_path("robot.xml")
           self._data = mujoco.MjData(self._model)

       def reset(self, object_start_x=0.0, object_start_y=0.0) -> None:
           """Called before each scenario. OSC parameters with matching names
           are injected automatically as keyword arguments."""
           import mujoco
           mujoco.mj_resetData(self._model, self._data)
           self._data.qpos[:2] = [object_start_x, object_start_y]

       def step(self) -> None:
           """Advance the simulation by one timestep (dt seconds).
           Must be non-blocking."""
           import mujoco
           mujoco.mj_step(self._model, self._data)

       def shutdown(self) -> None:
           """Called once after all scenarios complete."""
           self._model = None
           self._data = None

**Passing scenario parameters to the simulation**

Declare the OSC parameters you need directly as arguments on your ``reset()``
override. The framework matches argument names to OSC parameter names and
injects values automatically:

.. code-block:: osc

   scenario my_scenario:
       object_start_x: float = 0.0   # metres
       object_start_y: float = 0.0
       object_mass:    float = 1.0   # kg (not consumed by reset)

   action my_scenario.run():
       do serial:
           wait elapsed(5.0s)

.. code-block:: python

   def reset(self, object_start_x, object_start_y, gravity=9.81):
       # object_start_x / object_start_y injected from OSC
       # gravity uses its Python default because it is not in the scenario
       ...

Required arguments (no default) that are absent from the scenario file cause
a clear error before ``reset()`` is ever called.  Optional arguments (with
defaults) are passed when the scenario declares them, otherwise the default
is used.  Struct parameters are passed as nested dicts.

If a ``--scenario-parameter-file`` is supplied the overridden values are
applied before ``reset()`` is called.

The ``SimulationInterface`` lifecycle is aligned with the
`ros-simulation/simulation_interfaces <https://github.com/ros-simulation/simulation_interfaces>`_ standard:

.. list-table::
   :header-rows: 1

   * - ``SimulationInterface`` method
     - ``simulation_interfaces`` equivalent
   * - ``setup()``
     - Load world + simulator launch
   * - ``reset()``
     - ``ResetSimulation`` service (``SCOPE_ALL``)
   * - ``step()``
     - ``StepSimulation(steps=1)`` service
   * - ``shutdown()``
     - ``SetSimulationState(STATE_QUITTING)``

**Running a scenario with a simulation**

Pass the ``--simulation`` flag with the fully-qualified class path:

.. code-block:: bash

   scenario_execution --simulation my_pkg.my_sim:MySimulation my_scenario.osc

**Accessing the simulation from behaviors**

Behaviors receive the simulation object via ``kwargs['simulation']`` in their
``setup()`` method — the same pattern as ROS behaviors using ``kwargs['node']``:

.. code-block:: python

   from scenario_execution.actions.base_action import BaseAction
   import py_trees

   class ReadSensor(BaseAction):

       def setup(self, **kwargs):
           self.sim = kwargs['simulation']

       def update(self):
           obs = self.sim.get_observation()
           if obs['done']:
               return py_trees.common.Status.SUCCESS
           return py_trees.common.Status.RUNNING

**Time-based waits with simulation clock**

The ``wait elapsed()`` directive and ``timeout()`` modifier automatically use
the :class:`SimulationClock <scenario_execution.SimulationClock>` when a
simulation is active. No changes to the OSC scenario file are needed:

.. code-block::

   scenario test:
       do serial:
           wait elapsed(1s)   # counts 1 / dt simulation steps, not wall-clock seconds

Without a simulation interface the clock falls back to system wall-clock time,
so existing scenarios continue to work unchanged.

