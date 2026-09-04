OpenSCENARIO DSL
================

General
-------

This tool supports a subset of the `OpenSCENARIO DSL <https://www.asam.net/standards/detail/openscenario-dsl/>`__ standard.

The official documentation is available
`here <https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/latest/index.html>`__.

The `standard library of
OSC2 <https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/domain-model/_attachments/ASAM_OpenSCENARIO_DSL_v2.2.0_Domain_model_library.zip>`__
was adapted to be usable by the current parsing support of scenario execution.


Mapping to py-trees
-------------------

.. list-table:: 
   :widths: 15 25 60
   :header-rows: 1
   :class: tight-table   
   
   - * OpenScenario2  
     * py-trees
     * Comment
   - * ``action``
     * ``Behaviour``
     * Actions are derived from ``scenario_execution.actions.base_action.BaseAction`` which is derived from ``py_trees.behaviour.Behaviour``
   - * ``event``
     * blackboard entry and ``Behaviour``
     * ``Behaviour`` is used to read and write blackboard variable
   - * ``modifier``
     * ``Decorator``
     *
   - * ``var``
     * blackboard entry
     * Variables are stored within the blackboard


.. role:: raw-html(raw)
   :format: html

Supported features
------------------

In the following the OpenSCENARIO DSL keywords are listed with their current support status.


======================= ==================== =============================
Element Tag             Support              Notes
======================= ==================== =============================
``action``              :raw-html:`&#9989;`  partially, see details below      
``actor``               :raw-html:`&#9989;`  partially, see details below      
``as``                  :raw-html:`&#10060;`       
``bool``                :raw-html:`&#9989;`          
``call``                :raw-html:`&#10060;`       
``cover``               :raw-html:`&#10060;`       
``def``                 :raw-html:`&#9989;`  only ``external``
``default``             :raw-html:`&#10060;`      
``do``                  :raw-html:`&#9989;`          
``elapsed``             :raw-html:`&#9989;`           
``emit``                :raw-html:`&#9989;`              
``enum``                :raw-html:`&#9989;`              
``event``               :raw-html:`&#9989;`              
``every``               :raw-html:`&#10060;`        
``expression``          :raw-html:`&#9989;`
``extend``              :raw-html:`&#10060;`        
``external``            :raw-html:`&#10060;`      
``fall``                :raw-html:`&#10060;`          
``float``               :raw-html:`&#9989;`    
``global``              :raw-html:`&#9989;`       
``hard``                :raw-html:`&#10060;`         
``if``                  :raw-html:`&#10060;`       
``import``              :raw-html:`&#9989;`    
``inherits``            :raw-html:`&#9989;`    
``int``                 :raw-html:`&#9989;`    
``is``                  :raw-html:`&#10060;`         
``it``                  :raw-html:`&#9989;`    
``keep``                :raw-html:`&#9989;`    
``list``                :raw-html:`&#9989;`    
``of``                  :raw-html:`&#9989;`        
``on``                  :raw-html:`&#10060;` 
``one_of``              :raw-html:`&#9989;`        
``only``                :raw-html:`&#10060;`      
``parallel``            :raw-html:`&#9989;`         
``range``               :raw-html:`&#10060;`        
``record``              :raw-html:`&#10060;`   
``remove_default``      :raw-html:`&#10060;`   
``rise``                :raw-html:`&#10060;`   
``scenario``            :raw-html:`&#9989;`     
``serial``              :raw-html:`&#9989;`     
``SI``                  :raw-html:`&#9989;`     
``string``              :raw-html:`&#9989;`     
``struct``              :raw-html:`&#9989;`   
``type``                :raw-html:`&#9989;`       
``uint``                :raw-html:`&#9989;`    
``undefined``           :raw-html:`&#10060;`     
``unit``                :raw-html:`&#9989;`       
``until``               :raw-html:`&#10060;`        
``var``                 :raw-html:`&#9989;`         
``wait``                :raw-html:`&#9989;`        
``with``                :raw-html:`&#9989;`        
======================= ==================== =============================


Composition Types
^^^^^^^^^^^^^^^^^

Composition types are ``struct``, ``actor``, ``action``, ``scenario``.

============== ==================== ===========================
Element Type   Support              Notes
============== ==================== ===========================
Event          :raw-html:`&#9989;`      
Field          :raw-html:`&#9989;`     
Constraint     :raw-html:`&#9989;`  partially
Method         :raw-html:`&#9989;`       
Coverage       :raw-html:`&#10060;`       
Modifier       :raw-html:`&#9989;`  partially (only predefined)     
============== ==================== ===========================

Patterns
--------

Short, working answers to "how do I express this in a scenario", using the subset described above.
Each entry is a shape that has been run, not a sketch.

This section is meant to grow: add to it whenever a use case takes more than one attempt to express,
so the next reader finds the answer instead of rediscovering it. Keep the same form -- when to reach
for it, the scenario, and any caveat that would otherwise be found the hard way.

Stopping a running action
^^^^^^^^^^^^^^^^^^^^^^^^^

Stop after a fixed time, and check what came of it
""""""""""""""""""""""""""""""""""""""""""""""""""

When the cancellation *is* the thing under test -- did the server honor it?

.. code-block:: none

    action_call(action_name: '/backup',
                action_type: 'nav2_msgs.action.BackUp',
                data: '{\"target\": {\"x\": 0.5}, \"speed\": 0.5}',
                expected_status: action_goal_status!canceled) with:
        cancel_after(0.5s)

The action keeps running just long enough to report its terminal status, and ``expected_status``
turns that into the assertion. This is the only form that can tell "the goal was canceled" from "the
server ignored us and finished anyway".

Stop after a fixed time, without checking
"""""""""""""""""""""""""""""""""""""""""

When the action is scaffolding -- a recording, a background load -- and only the stopping matters.

.. code-block:: none

    one_of:
        ros_bag_record(topics: ['/scan', '/odom'])
        wait elapsed(30s)

The timer finishing ends the other branch, and the action is stopped on the way out.

.. caution::

    ``one_of`` cannot report *whether* the action stopped. An action that does not support
    cancellation is left running until the scenario ends, silently. Use the form above when that
    distinction matters.

Stop when something happens
"""""""""""""""""""""""""""

Same shape, with a condition in place of the timer:

.. code-block:: none

    one_of:
        nav_to_pose(goal_pose: ...)
        wait_for_data(topic_name: '/obstacle_detected', topic_type: 'std_msgs.msg.Bool')

Stop from another branch
""""""""""""""""""""""""

When the condition is established elsewhere in the scenario, carry it as an ``event``. The emitting
branch decides *when*, the waiting branch decides *what it ends*, and neither refers to the other.

.. code-block:: none

    scenario cancel_on_event:
        event obstacle_detected
        do parallel:
            serial:
                one_of:
                    nav_to_pose(goal_pose: ...)
                    wait @obstacle_detected
                emit end
            serial:
                wait_for_data(topic_name: '/obstacle_detected', topic_type: 'std_msgs.msg.Bool')
                emit obstacle_detected

This is the way to reach across branches. There is no way to name a running action and act on it
directly, and there should not be: an event goes through the blackboard, so the two branches stay
independent of each other's structure.

Calling actions
^^^^^^^^^^^^^^^

Send a second goal while the first is still running
"""""""""""""""""""""""""""""""""""""""""""""""""""

To exercise a server's preemption, the first call must not block its branch. ``success_on_acceptance``
finishes it at goal acceptance and leaves the goal running for the second to supersede.

.. code-block:: none

    do parallel:
        action_call(action_name: '/spin', ..., success_on_acceptance: true)
        serial:
            wait elapsed(0.5s)
            action_call(action_name: '/spin', ...)

The second call waits for the terminal status, so it carries the assertion.

Expect a goal to be rejected or to fail
"""""""""""""""""""""""""""""""""""""""

``expected_status`` is not only for cancellation. Asserting that a bad goal is refused:

.. code-block:: none

    action_call(action_name: '/compute_path_to_pose',
                action_type: 'nav2_msgs.action.ComputePathToPose',
                data: '{...}',
                expected_status: action_goal_status!aborted)

Inspecting another action
^^^^^^^^^^^^^^^^^^^^^^^^^

Wait for a process to log something
"""""""""""""""""""""""""""""""""""

Label the process, then name the label:

.. code-block:: none

    do serial:
        app: run_process('./server')
        process_log_check('app', ['Ready'])

Combining modifiers
^^^^^^^^^^^^^^^^^^^

Modifiers stack, and they nest: the one written **last** ends up closest to the action.

.. code-block:: none

    run_process('./load-generator') with:
        cancel_after(30s)
        failure_is_success()

``cancel_after`` stops the process and reports what the process made of that -- a failure, since it
was killed -- and ``failure_is_success()`` turns that into the verdict the scenario wants.

Things that are usually looked for first
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The keyword table above is the full answer, but two absences send people looking for a pattern that
does not exist. There is no conditional branch: ``if`` is unsupported, and choosing between two
courses of action is expressed by which branch of a ``one_of`` finishes first. And ``emit end`` /
``emit fail`` end the whole scenario rather than the branch they appear in -- to end one branch, let
it finish.
