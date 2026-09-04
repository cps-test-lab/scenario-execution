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

import copy
import py_trees
from py_trees.common import Access, Status
from importlib.metadata import entry_points
import inspect

from scenario_execution.model.types import KeepConstraintDeclaration, visit_expression, ActionDeclaration, BinaryExpression, EventReference, Expression, FunctionApplicationExpression, ModifierInvocation, ScenarioDeclaration, DoMember, WaitDirective, EmitDirective, BehaviorInvocation, EventCondition, EventDeclaration, RelationExpression, LogicalExpression, ElapsedExpression, PhysicalLiteral, ModifierDeclaration
from scenario_execution.clock_behaviors import ClockTimer, ClockTimeout
from scenario_execution.model.model_base_visitor import ModelBaseVisitor
from scenario_execution.model.error import OSC2ParsingError
from scenario_execution.actions.base_action import BaseAction
from scenario_execution.actions.base_action_subtree import BaseActionSubtree


def create_py_tree(model, tree, logger, log_tree):
    model_to_py_tree = ModelToPyTree(logger)
    try:
        final_tree = model_to_py_tree.build(model, tree, log_tree)
    except OSC2ParsingError as e:
        raise ValueError(f'Error while creating py-tree: {e}') from e
    return final_tree


class TopicEquals(py_trees.behaviour.Behaviour):
    """
    Class to listen to a topic in Blackboard and check if it equals the defined message

    Args:
        key [str]: topic to listen to
        msg [str]: target message to match
        namespace [str]: namespace of the key
    """

    def __init__(self, key: str, msg: str, namespace: str = None):
        super().__init__(self.__class__.__name__)

        self.namespace = namespace
        self.key = key
        self.msg = msg

        self.client = self.attach_blackboard_client(namespace=self.namespace)
        self.client.register_key(self.key, access=Access.READ)

    def update(self):
        """
        Check the message on the topic equals the target message
        """
        msg_on_blackboard = self.client.get(self.key)
        if msg_on_blackboard == self.msg:
            return Status.SUCCESS
        return Status.RUNNING


class TopicPublish(py_trees.behaviour.Behaviour):
    """
    Class to publish a message to a topic

    Args:
        key [str]: topic to publish on
        msg [str]: message to publish on that topic
        namespace [str]: namespace of the key
    """

    def __init__(self, name: "TopicPublish", key: str, msg: str, namespace: str = None):
        super().__init__(name)

        self.namespace = namespace
        self.key = key
        self.msg = msg

        self.client = self.attach_blackboard_client(namespace=self.namespace)
        self.client.register_key(self.key, access=Access.WRITE)

    def setup(self, **kwargs):
        """
        Setup empty topic on blackboard

        This is to prevent the "Reader" from reading before the topic exists.
        """
        self.client.set(self.key, '')

    def update(self):
        """
        publish the message to topic
        """
        self.client.set(self.key, self.msg)
        return Status.SUCCESS


class ExpressionBehavior(BaseAction):  # py_trees.behaviour.Behaviour):

    def __init__(self, name: "ExpressionBehavior", expression: Expression, model, logger):
        super().__init__(resolve_variable_reference_arguments_in_execute=False)
        self._set_base_properities(name, model, logger)
        self.expression = expression

    def update(self):
        if self.expression.eval(self.get_blackboard_client()):
            return Status.SUCCESS
        else:
            return Status.RUNNING


class ModelToPyTree(object):

    def __init__(self, logger):
        self.logger = logger

    def build(self, model, tree, log_tree):

        self.blackboard = tree.attach_blackboard_client(name="ModelToPyTree")
        behavior_builder = self.BehaviorInit(self.logger, tree)
        behavior_builder.visit(model)

        if log_tree:
            print(py_trees.display.ascii_tree(tree))
        return behavior_builder.tree

    class BehaviorInit(ModelBaseVisitor):
        def __init__(self, logger, tree) -> None:
            super().__init__()
            self.logger = logger
            self.blackboard = None
            if not isinstance(tree, py_trees.composites.Sequence):
                raise ValueError("ModelToPyTree requires a py-tree sequence as input")
            self.tree = tree
            self.__cur_behavior = tree
            # One entry per subtree currently being built, each holding the `with:` members that
            # apply to it. A subtree nests, so this is a stack.
            self.__with_blocks = []

        @staticmethod
        def stamp_source(behavior, node):
            """Record which .osc element a behaviour came from, as (file, line, column).

            Only plugin actions can be traced back today, and only indirectly, via the
            model they keep in BaseAction._model. Composites, decorators and the built-in
            behaviours below are plain py_trees objects with no model reference at all, so
            anything reading a tree at runtime -- a status log, a debugger -- cannot say
            which line of the scenario a node came from. Stamping every behaviour here
            keeps that uniform. Line is 1-based, column 0-based, straight from ANTLR.

            The file comes from the model element rather than the entry scenario because
            an imported .osc carries its own name (model_builder passes current_file).
            """
            line, column, _, filename = node.get_ctx()
            behavior.osc_source = (filename, line, column)

        def visit_scenario_declaration(self, node: ScenarioDeclaration):
            scenario_name = node.qualified_behavior_name

            self.__cur_behavior.name = scenario_name
            self.stamp_source(self.__cur_behavior, node)

            self.blackboard = self.__cur_behavior.attach_blackboard_client(
                name="ModelToPyTree")

            self._push_with_block()
            super().visit_scenario_declaration(node)
            self._apply_with_block(self.__cur_behavior)

        def visit_do_member(self, node: DoMember):
            composition_operator = node.composition_operator
            name = node.name
            if not name:
                name = composition_operator
            if composition_operator == "serial":
                behavior = py_trees.composites.Sequence(name=name, memory=True)
            elif composition_operator == "parallel":
                behavior = py_trees.composites.Parallel(name=name, policy=py_trees.common.ParallelPolicy.SuccessOnAll())
            elif composition_operator == "one_of":
                behavior = py_trees.composites.Parallel(name=name, policy=py_trees.common.ParallelPolicy.SuccessOnOne())
            else:
                raise NotImplementedError(f"scenario operator {composition_operator} not yet supported.")

            self.stamp_source(behavior, node)
            parent = self.__cur_behavior
            self.__cur_behavior.add_child(behavior)
            self.__cur_behavior = behavior
            self._push_with_block()
            self.visit_children(node)
            self._apply_with_block(behavior)
            self.__cur_behavior = parent

        def visit_wait_directive(self, node: WaitDirective):
            child = node.get_only_child()

            if isinstance(child, (EventCondition, EventReference)):
                behavior = self.visit(child)

                self.stamp_source(behavior, node)
                self.__cur_behavior.add_child(behavior)
            else:
                raise OSC2ParsingError(msg="Invalid wait directive.", context=node.get_ctx())

        def visit_emit_directive(self, node: EmitDirective):
            if node.event_name in ['start', 'end', 'fail']:
                scenario_elem = node
                while scenario_elem is not None and not isinstance(scenario_elem, ScenarioDeclaration):
                    scenario_elem = scenario_elem.get_parent()
                behavior = TopicPublish(
                    name=f"emit {node.event_name}", key=f"/{scenario_elem.name}/{node.event_name}", msg=True)
            else:
                qualified_name = node.event.get_qualified_name()
                behavior = TopicPublish(
                    name=f"emit {node.event_name}", key=qualified_name, msg=True)
            self.stamp_source(behavior, node)
            self.__cur_behavior.add_child(behavior)

        def compare_method_arguments(self, method, expected_args, behavior_name, node):
            method_args = inspect.getfullargspec(method).args

            if "self" not in method_args:
                raise OSC2ParsingError(
                    msg=f'Plugin {behavior_name} {method.__name__} method is missing argument "self".', context=node.get_ctx())

            unexpected_args = []
            missing_args = copy.copy(expected_args)
            for element in method_args:
                if element not in expected_args:
                    unexpected_args.append(element)
                else:
                    missing_args.remove(element)
            return method_args, unexpected_args, missing_args

        def build_decorator(self, node: ModifierDeclaration, resolved_values, child, invocation=None):
            """Construct the decorator a modifier stands for, wrapping *child*.

            Building and placing are separate: a ``with:`` block is applied as a whole once its
            subtree is complete, so nothing here touches a parent.
            """
            # *node* is the modifier's declaration, which for a built-in modifier lives in
            # an imported library -- useless as a source anchor. *invocation* is the call
            # site in the scenario, which is what a reader wants to be pointed at.
            source_node = invocation if invocation is not None else node
            available_modifiers = ["repeat", "inverter", "timeout", "retry",
                                   "failure_is_running", "failure_is_success",
                                   "running_is_failure", "running_is_success", "success_is_failure", "success_is_running"]
            if node.name not in available_modifiers:
                # fall back to installed modifier plugins
                modifier_eps = entry_points(group='scenario_execution.modifiers')
                for ep in modifier_eps:
                    if ep.name == node.name:
                        factory = ep.load()
                        instance = factory(child, resolved_values)
                        self.stamp_source(instance, source_node)
                        return instance
                raise OSC2ParsingError(
                    msg=f'Unknown modifier "{node.name}". Available built-in modifiers: {available_modifiers}. No plugin found either.', context=node.get_ctx())
            if node.name == "repeat":
                instance = py_trees.decorators.Repeat(name="repeat", child=child, num_success=resolved_values["count"])
            elif node.name == "inverter":
                instance = py_trees.decorators.Inverter(name="inverter", child=child)
            elif node.name == "timeout":
                instance = ClockTimeout(name="timeout", child=child, duration=resolved_values["duration"])
            elif node.name == "retry":
                instance = py_trees.decorators.Retry(name="retry", child=child, num_failures=resolved_values["count"])
            elif node.name == "failure_is_running":
                instance = py_trees.decorators.FailureIsRunning(name="failure_is_running", child=child)
            elif node.name == "failure_is_success":
                instance = py_trees.decorators.FailureIsSuccess(name="failure_is_success", child=child)
            elif node.name == "running_is_failure":
                instance = py_trees.decorators.RunningIsFailure(name="running_is_failure", child=child)
            elif node.name == "running_is_success":
                instance = py_trees.decorators.RunningIsSuccess(name="running_is_success", child=child)
            elif node.name == "success_is_failure":
                instance = py_trees.decorators.SuccessIsFailure(name="success_is_failure", child=child)
            elif node.name == "success_is_running":
                instance = py_trees.decorators.SuccessIsRunning(name="success_is_running", child=child)
            else:
                raise ValueError('unknown modifier (should not reach here).')

            self.stamp_source(instance, source_node)
            return instance

        def _push_with_block(self):
            """Start collecting the ``with:`` members that apply to the subtree about to be built."""
            self.__with_blocks.append([])

        def _apply_with_block(self, target):
            """Wrap *target* in what its ``with:`` block collected, and put it in place once.

            Modifiers nest, and the one written last ends up closest to the action, so the block is
            applied back to front. Building the whole stack before touching the tree is what keeps
            that order stated here rather than emerging from repeated re-parenting.
            """
            modifiers = self.__with_blocks.pop()
            if not modifiers:
                return
            parent = target.parent
            if parent:
                parent.children.remove(target)
                target.parent = None

            wrapped = target
            for declaration, resolved_values, invocation, error_prefix in reversed(modifiers):
                try:
                    wrapped = self.build_decorator(declaration, resolved_values, wrapped, invocation)
                except ValueError as e:
                    raise OSC2ParsingError(msg=f'{error_prefix} {e}.', context=invocation.get_ctx()) from e

            name, context = modifiers[0][0].name, modifiers[0][2]
            if isinstance(parent, py_trees.composites.Composite):
                parent.add_child(wrapped)
            elif isinstance(parent, py_trees.decorators.Decorator):
                parent.children.append(wrapped)
                parent.decorated = wrapped
                wrapped.parent = parent
            elif not parent:
                # the name is used as a blackboard key later, so the wrapper takes the child's
                wrapped.name = target.name
                self.tree = wrapped
            else:
                raise OSC2ParsingError(
                    msg=f'Modifier "{name}" found at unsupported location.', context=context.get_ctx())

        def visit_behavior_invocation(self, node: BehaviorInvocation):
            if isinstance(node.behavior, ModifierDeclaration):
                resolved_values = node.get_resolved_value(self.blackboard)
                self.__with_blocks[-1].append(
                    (node.behavior, resolved_values, node, f'Modifier "{node.behavior.name}"'))
            elif isinstance(node.behavior, ActionDeclaration):
                behavior_name = node.behavior.name
                available_plugins = []
                action_eps = entry_points(group='scenario_execution.actions')

                for entry_point in action_eps:
                    # self.logger.debug(f'entry_point.name is {entry_point.name}')
                    if entry_point.name == behavior_name:
                        available_plugins.append(entry_point)
                if not available_plugins:
                    raise OSC2ParsingError(
                        msg=f'No plugins found for action "{behavior_name}".',
                        context=node.get_ctx()
                    )
                if len(available_plugins) > 1:
                    self.logger.error(f'More than one plugin is found for "{behavior_name}".')
                    for available_plugin in available_plugins:
                        self.logger.error(
                            f'Found available plugin for "{behavior_name}" '
                            f'in module "{available_plugin.module_name}".')
                    raise OSC2ParsingError(
                        msg=f'More than one plugin is found for "{behavior_name}".',
                        context=node.get_ctx()
                    )
                behavior_cls = available_plugins[0].load()

                if not issubclass(behavior_cls, BaseAction) and not issubclass(behavior_cls, BaseActionSubtree) :
                    raise OSC2ParsingError(
                        msg=f"Found plugin for '{behavior_name}', but it's not derived from BaseAction or BaseActionSubtree.",
                        context=node.get_ctx()
                    )

                expected_args = ["self"]
                if node.actor:
                    expected_args.append("associated_actor")
                expected_args += node.get_parameter_names()

                # check plugin constructor
                init_method = getattr(behavior_cls, "__init__", None)
                init_args = None
                if init_method is not None:
                    # if __init__() is defined, check parameters. Allowed:
                    # - __init__(self)
                    # - __init__(self, resolve_variable_reference_arguments_in_execute)
                    # - __init__(self, <some-or-all-osc-defined-args>)
                    init_args, unexpected_args, args_not_in_init = self.compare_method_arguments(
                        init_method, expected_args, behavior_name, node)
                    if init_args != ["self"] and \
                            init_args != ["self", "resolve_variable_reference_arguments_in_execute"] and \
                            not all(x in expected_args for x in init_args):
                        raise OSC2ParsingError(
                            msg=f'Plugin {behavior_name}: __init__() either only has "self" argument and osc-defined arguments. Unexpected args: {", ".join(unexpected_args)}\n'
                                f'expected definition with all arguments: {expected_args}', context=node.get_ctx()
                        )
                execute_method = getattr(behavior_cls, "execute", None)
                if execute_method is None:
                    if args_not_in_init:
                        raise OSC2ParsingError(
                            msg=f'Plugin {behavior_name}: execute() required, but not defined. Required arguments (i.e. not defined in __init__()): {", ".join(args_not_in_init)}.', context=node.get_ctx())
                else:
                    expected_execute_args = copy.deepcopy(args_not_in_init)
                    expected_execute_args.append("self")
                    if node.actor:
                        expected_execute_args.append("associated_actor")
                    _, unexpected_execute_args, missing_execute_args = self.compare_method_arguments(
                        execute_method, expected_execute_args, behavior_name, node)
                    if missing_execute_args:
                        raise OSC2ParsingError(
                            msg=f'Plugin {behavior_name}: execute() is missing arguments: {", ".join(missing_execute_args)}. Either specify in __init__() or execute().', context=node.get_ctx())
                    if unexpected_execute_args:
                        error = ""
                        if any(x in init_args for x in unexpected_execute_args):
                            error = " osc2 arguments, that are consumed in __init__() are not allowed to be used in execute() again. Please either remove argument(s) from __init__() or execute()."
                        raise OSC2ParsingError(
                            msg=f'Plugin {behavior_name}: execute() has unexpected arguments: {", ".join(unexpected_execute_args)}.{error}', context=node.get_ctx())

                # initialize plugin instance
                action_name = node.name
                if not action_name:
                    action_name = behavior_name
                self.logger.debug(f"Instantiate action '{action_name}', plugin '{behavior_name}'.")
                try:
                    if init_args is not None and init_args != ['self'] and init_args != ['self', 'resolve_variable_reference_arguments_in_execute']:
                        final_args = node.get_resolved_value(self.blackboard, skip_keys=args_not_in_init)

                        if node.actor:
                            final_args["associated_actor"] = node.actor.get_resolved_value(self.blackboard)
                            final_args["associated_actor"]["name"] = node.actor.name

                        instance = behavior_cls(**final_args)
                        remote_init_args = final_args
                    else:
                        instance = behavior_cls()
                        remote_init_args = {}
                    instance._set_base_properities(action_name, node, self.logger)  # pylint: disable=protected-access
                    # attributes used by scenario_execution_remote modifier
                    instance._external_plugin_key = available_plugins[0].name  # pylint: disable=protected-access
                    instance._external_init_args = remote_init_args  # pylint: disable=protected-access
                except Exception as e:
                    raise OSC2ParsingError(msg=f'Error while initializing plugin {behavior_name}: {e}', context=node.get_ctx()) from e
                self.stamp_source(instance, node)
                self.__cur_behavior.add_child(instance)
                previous = self.__cur_behavior
                self.__cur_behavior = instance
                self._push_with_block()
                super().visit_behavior_invocation(node)

		# For BaseActionSubtree, check create_subtree method instead of execute
                create_subtree_method = getattr(behavior_cls, "create_subtree", None)
                if issubclass(behavior_cls, BaseActionSubtree) and create_subtree_method is not None:
                    create_subtree_method(self.__cur_behavior)
                self._apply_with_block(instance)
                self.__cur_behavior = previous

        def visit_event_reference(self, node: EventReference):
            event = node.resolve(node.event_path)
            name = event.get_qualified_name()
            return TopicEquals(key=name, msg=True)

        def visit_event_condition(self, node: EventCondition):
            expression = ""
            for child in node.get_children():
                if isinstance(child, (RelationExpression, LogicalExpression)):
                    expression = ExpressionBehavior(name=node.get_ctx()[2], expression=self.visit(child), model=node, logger=self.logger)
                elif isinstance(child, ElapsedExpression):
                    elapsed_condition = self.visit_elapsed_expression(child)
                    expression = ClockTimer(name=f"wait {elapsed_condition}s", duration=float(elapsed_condition))
                else:
                    raise OSC2ParsingError(
                        msg=f'Invalid event condition {child}', context=node.get_ctx())
            return expression

        def visit_relation_expression(self, node: RelationExpression):
            return visit_expression(node, self.blackboard)

        def visit_logical_expression(self, node: LogicalExpression):
            return visit_expression(node, self.blackboard)

        def visit_binary_expression(self, node: BinaryExpression):
            return visit_expression(node, self.blackboard)

        def visit_elapsed_expression(self, node: ElapsedExpression):
            elem = node.find_first_child_of_type(PhysicalLiteral)
            if not elem:
                elem = node.find_first_child_of_type(FunctionApplicationExpression)

            if not elem:
                raise OSC2ParsingError(
                    msg=f'Elapsed expression currently only supports PhysicalLiteral and FunctionApplicationExpression.', context=node.get_ctx())

            return elem.get_resolved_value()

        def visit_event_declaration(self, node: EventDeclaration):
            if node.name in ['start', 'end', 'fail']:
                raise OSC2ParsingError(
                    msg=f'EventDeclaration uses reserved name {node.name}.', context=node.get_ctx()
                )
            else:
                qualified_name = node.get_qualified_name()
                client = self.__cur_behavior.attach_blackboard_client()
                client.register_key(qualified_name, access=Access.WRITE)
                setattr(client, qualified_name, None)

        def visit_modifier_invocation(self, node: ModifierInvocation):
            resolved_values = node.get_resolved_value()
            self.__with_blocks[-1].append((node.modifier, resolved_values, node, 'ModifierDeclaration'))

        def visit_keep_constraint_declaration(self, node: KeepConstraintDeclaration):
            # skip relation-expression
            pass
