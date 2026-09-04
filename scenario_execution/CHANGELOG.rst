^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package scenario_execution
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1.6.0 (2026-09-04)
------------------
* Support the until directive, and the if guard on an event reference (`#88 <https://github.com/cps-test-lab/scenario-execution/issues/88>`_)
* Cancel a long-running action mid-scenario, not only at teardown (`#85 <https://github.com/cps-test-lab/scenario-execution/issues/85>`_)
* Keep a bool parameter override true when the parameter has a default (`#86 <https://github.com/cps-test-lab/scenario-execution/issues/86>`_)
* Record how fast the tree ticked, and which behavior spent the time (`#84 <https://github.com/cps-test-lab/scenario-execution/issues/84>`_)
* Drop the lexer predicate that defeats ANTLR's DFA cache (`#82 <https://github.com/cps-test-lab/scenario-execution/issues/82>`_)
* Get latest scenario state (`#81 <https://github.com/cps-test-lab/scenario-execution/issues/81>`_)
* Extend the introspection interface: get_action_details, describe_scenario, and a standalone MCP server (`#79 <https://github.com/cps-test-lab/scenario-execution/issues/79>`_)
* add introspection interface (`#75 <https://github.com/cps-test-lab/scenario-execution/issues/75>`_)
* Tracing (`#76 <https://github.com/cps-test-lab/scenario-execution/issues/76>`_)
* Feature/process log check (`#74 <https://github.com/cps-test-lab/scenario-execution/issues/74>`_)
* Contributors: Florian Mirus, fred-labs

1.5.0 (2026-06-14)
------------------
* Support step-based simulators
* Fix for python 3.13 (`#65 <https://github.com/cps-test-lab/scenario-execution/issues/65>`_)
* support multiple --post-run (`#63 <https://github.com/cps-test-lab/scenario-execution/issues/63>`_)
* Support adding modifiers (`#60 <https://github.com/cps-test-lab/scenario-execution/issues/60>`_)
* improve error message (`#57 <https://github.com/cps-test-lab/scenario-execution/issues/57>`_)
* add custom field in junit xml: start_time (`#56 <https://github.com/cps-test-lab/scenario-execution/issues/56>`_)
* run_process: fix cleanup (`#55 <https://github.com/cps-test-lab/scenario-execution/issues/55>`_)
* Update pytrees version (`#53 <https://github.com/cps-test-lab/scenario-execution/issues/53>`_)
* Contributors: Adi Vardi, Frederik Pasch

1.4.0 (2025-11-27)
------------------
* Add external interface
* support creating override template
* Fix overriding list parameters
* Allow overriding non-initialized parameters
* add ability to set snapshot period
* add post command execution
* Add directory getters

1.3.0 (2025-06-04)
------------------
* add ros examples and new actions
* update run_process action to send signals to whole process group. add ros_run action

1.2.1 (2025-05-27)
------------------
* update py-trees dependency
* update from OpenSCENARIO 2.0 to OpenSCENARIO DSL V2.1.0

1.2.0 (2024-10-02)
------------------
* Commandline parameters
* Add increment, decrement action, fix check
* Initialize osc args only once, either in init or execute
* Add support for expressions
* Change to lenient pyyaml requirements
* model antlr4 dependency correctly
* Cleanup logger access
* Add basic support for Modifiers
* update py-trees dependency to 2.2.3
* Support writing dot-files
* Support variables, references to members, late-initialization
* Add support for external methods
* Write output file on parsing error
