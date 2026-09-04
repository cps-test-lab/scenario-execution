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
``expression``          :raw-html:`&#10060;` method bodies are ``external`` only
``extend``              :raw-html:`&#10060;`
``external``            :raw-html:`&#9989;`  method implementation qualifier
``fall``                :raw-html:`&#10060;`
``float``               :raw-html:`&#9989;`
``global``              :raw-html:`&#9989;`
``hard``                :raw-html:`&#10060;`
``if``                  :raw-html:`&#9989;`  guards an event reference, see below
``import``              :raw-html:`&#9989;`
``inherits``            :raw-html:`&#9989;`
``int``                 :raw-html:`&#9989;`
``is``                  :raw-html:`&#9989;`
``it``                  :raw-html:`&#9989;`
``keep``                :raw-html:`&#9989;`
``list``                :raw-html:`&#9989;`
``of``                  :raw-html:`&#9989;`
``on``                  :raw-html:`&#10060;`
``one_of``              :raw-html:`&#9989;`
``only``                :raw-html:`&#9989;`  method implementation qualifier
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
``until``               :raw-html:`&#9989;`
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

Stop after a fixed time
"""""""""""""""""""""""

When the action is scaffolding -- a recording, a background load -- and only the stopping matters.

.. code-block:: none

    ros_bag_record(topics: ['/scan', '/odom']) with:
        until elapsed(30s)

``until`` bounds the action it is written on: the action runs, and ends the moment the condition
holds. Written as a ``one_of`` against a timer it means the same thing, and is what to reach for
when the two really are peers rather than an action and the thing that stops it.

.. caution::

    ``until`` ends the action's branch by invalidating it, so the action reports no status: this
    shape can show that the timer fired, never that the action stopped or how it ended. An action
    that does not support cancellation is left running until the scenario ends, silently. For a ROS
    action whose cancellation is itself the thing under test, ``action_call()`` takes ``cancel_after``
    and ``expected_status`` instead.

Stop when something happens
"""""""""""""""""""""""""""

``until`` takes an event specification -- an ``elapsed()``, an ``@event``, or a condition over
variables -- not an action:

.. code-block:: none

    scenario stop_on_count:
        var seen: int = 0
        do serial:
            nav_to_pose(goal_pose: ...) with:
                until seen == 3

Several ``until`` directives on one invocation end it on the first of them to occur.

When the thing to wait for is an *action* rather than a condition, it has to be a branch of its own,
which is what ``one_of`` is for:

.. code-block:: none

    one_of:
        nav_to_pose(goal_pose: ...)
        wait_for_data(topic_name: '/obstacle_detected', topic_type: 'std_msgs.msg.Bool')

Stop from another branch
""""""""""""""""""""""""

When the condition is established elsewhere in the scenario, carry it as an ``event``. The emitting
branch decides *when*, the ``until`` decides *what it ends*, and neither refers to the other.

.. code-block:: none

    scenario stop_on_event:
        event obstacle_detected
        do parallel:
            nav_to_pose(goal_pose: ...) with:
                until @obstacle_detected
            serial:
                wait_for_data(topic_name: '/obstacle_detected', topic_type: 'std_msgs.msg.Bool')
                emit obstacle_detected

This is the way to reach across branches. There is no way to name a running action and act on it
directly, and there should not be: an event goes through the blackboard, so the two branches stay
independent of each other's structure.

Bound a whole block
"""""""""""""""""""

A ``with:`` block on a composition applies to everything inside it, which is the case ``one_of``
cannot state without wrapping the block in another level first.

.. code-block:: none

    do serial:
        log(msg: 'collecting')
        run_process(command: 'sleep 60')
        log(msg: 'never reached')
    with:
        until elapsed(3s)

Require more than the event
"""""""""""""""""""""""""""

An event is a flag: once emitted it stays set, so the first ``emit`` ends the action. ``if`` guards
the event with a condition that is re-checked on every tick, and the action ends on the first tick
where both hold -- below, on the second batch rather than the first.

.. code-block:: none

    scenario until_guarded:
        event batch_done
        var batches: int = 0
        do parallel:
            run_process(command: 'sleep 60') with:
                until @batch_done if batches == 2
            serial:
                repeat(3)
                wait elapsed(1s)
                increment(batches)
                emit batch_done

Binding the event to a name with ``as`` is not supported: an event carries no payload here, so there
would be nothing for the name to hold.

.. note::

    Two places where this differs from the standard. Termination lands on the first tick at which
    the condition holds rather than at the instant of the event, which is true of every condition in
    a ticked tree. And the standard describes ``until`` only for a behavior invocation, leaving a
    ``with:`` block on a composition -- which its grammar allows -- unstated; the reading taken here
    is that the composition ends on the event.

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
        timeout(30s)
        failure_is_success()

``timeout()`` stops the process and reports failure, and ``failure_is_success()`` turns that into
the verdict the scenario wants. Order matters: the modifier written last ends up closest to the
action.
