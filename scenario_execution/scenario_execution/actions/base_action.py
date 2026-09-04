# Copyright (C) 2025 Frederik Pasch
# Copyright (C) 2024 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import py_trees
from scenario_execution.model.error import OSC2Error
import inspect
from .base_action_subtree import BaseActionSubtree


class BaseAction(py_trees.behaviour.Behaviour):

    # subclasses might implement __init__() with osc2 arguments as required
    # CAUTION: __init__() only gets the initial parameter values. In case variables get modified during scenario execution,
    #          the latest values are available in execute() only.
    def __init__(self, resolve_variable_reference_arguments_in_execute=True):
        self._model = None
        self.logger = None
        self.blackboard = None
        self.resolve_variable_reference_arguments_in_execute = resolve_variable_reference_arguments_in_execute

        execute_method = getattr(self, "execute", None)
        if execute_method is not None and callable(execute_method):
            self.execute_method = execute_method
            self.execute_skip_args = inspect.getfullargspec(getattr(self, "__init__", None)).args
        else:
            self.execute_method = None
        super().__init__(self.__class__.__name__)

    # Subclasses might implement execute() with the osc2 arguments that are not used within __init__().
    # def execute(self):

    # Subclasses might override shutdown() in order to cleanup on scenario shutdown.
    def shutdown(self):
        pass

    def request_cancel(self) -> bool:
        """Ask a long-running action to stop before it would finish on its own.

        Long-running actions -- a navigation goal, a recording, a background process -- override
        this to start their own graceful stop and return True. Returning False means "I cannot be
        cancelled", and callers turn that into a failure: a cancel that silently does nothing would
        let a scenario pass while the thing it meant to stop kept running.

        Must be idempotent. An action can be asked to stop through more than one route for the
        same stop -- terminate() on an invalidated branch, shutdown() at teardown, and whatever the
        action itself offers.
        """
        return False

    #############
    # Internal methods below, do not override in subclass
    #############

    def terminate(self, new_status):
        """Cancel the action when its branch is invalidated.

        py_trees invalidates a behaviour whose branch was abandoned: a losing one_of child, or one
        the timeout modifier gave up on. Without this the branch ends while the action's real-world
        effect -- a goal the robot is still driving, a container still running -- continues to the
        end of the scenario.

        Only INVALID means abandonment. py_trees also routes ordinary SUCCESS and FAILURE stops
        through terminate(), and cancelling there would tear down actions that just finished.
        """
        if new_status == py_trees.common.Status.INVALID:
            self.request_cancel()

    def initialise(self):
        if self.execute_method is not None:
            if isinstance(self.parent, BaseActionSubtree):
                # in case the parent action is a composite, get required values there
                final_args = self.parent.get_execution_args(self)
            else:
                if self.resolve_variable_reference_arguments_in_execute:
                    final_args = self._model.get_resolved_value(self.get_blackboard_client(), skip_keys=self.execute_skip_args)
                else:
                    try:
                        final_args = self._model.get_resolved_value_with_variable_references(
                            self.get_blackboard_client(), skip_keys=self.execute_skip_args)
                    except ValueError as e:
                        raise ActionError(f"Error initializing action: {e}", action=self) from e

                if self._model.actor:
                    final_args["associated_actor"] = self._model.actor.get_resolved_value(self.get_blackboard_client())
                    final_args["associated_actor"]["name"] = self._model.actor.name

            self.execute(**final_args)  # pylint: disable=no-member

    def _set_base_properities(self, name, model, logger):
        self.name = name
        self._model = model
        self.logger = logger

    def get_blackboard_client(self):
        if self.blackboard:
            return self.blackboard
        self.blackboard = self.attach_blackboard_client(name=self.name)
        return self.blackboard

    def register_access_to_associated_actor_variable(self, variable_name):
        if not self._model.actor:
            raise ActionError("Model does not have 'actor'.", action=self)
        blackboard = self.get_blackboard_client()
        model_blackboard_name = self._model.actor.get_qualified_name()
        model_blackboard_name += "/" + variable_name
        blackboard.register_key(model_blackboard_name, access=py_trees.common.Access.WRITE)
        return model_blackboard_name

    def set_associated_actor_variable(self, variable_name, value):
        model_blackboard_name = self.register_access_to_associated_actor_variable(variable_name)
        self.logger.debug(f"Set variable '{model_blackboard_name}' to '{value}'")
        setattr(self.get_blackboard_client(), model_blackboard_name, value)

    def get_associated_actor_variable(self, variable_name):
        model_blackboard_name = self.register_access_to_associated_actor_variable(variable_name)
        self.logger.debug(f"Get variable '{model_blackboard_name}'")
        return getattr(self.get_blackboard_client(), model_blackboard_name)

    def get_simulation(self, kwargs: dict):
        """Return the simulation object from setup kwargs, or raise a clear error.

        Use in setup(**kwargs) instead of kwargs['simulation'] directly so that
        forgetting --simulation produces a readable message rather than a KeyError.
        """
        sim = kwargs.get('simulation')
        if sim is None:
            raise ActionError(
                f"'{self.__class__.__name__}' requires a simulation but none was provided. "
                "Pass --simulation <module:Class> when running scenario_execution.",
                action=self,
            )
        return sim


class ActionError(OSC2Error):

    def __init__(self, msg: str, action: BaseAction, *args) -> None:
        if action is not None and action._model is not None:
            ctx = action._model.get_ctx()
        else:
            ctx = None
        super().__init__(msg, ctx, *args)
