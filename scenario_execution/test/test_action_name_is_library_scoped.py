# Copyright (C) 2026 Frederik Pasch
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
"""An action name is unique within a library, not across every installed package."""

import unittest

from scenario_execution.model import model_to_py_tree as m


class _Dist:
    def __init__(self, name):
        self.name = name


class _Plugin:
    """Stands in for an entry point: only ``dist.name`` is read when disambiguating."""

    def __init__(self, dist_name):
        self.dist = _Dist(dist_name)
        self.module_name = f"{dist_name}.actions.spawn_entity"


class _Decl:
    """Stands in for an ActionDeclaration: only its ctx's source path is read."""

    def __init__(self, source):
        self._source = source

    def get_ctx(self):
        return (1, 0, "action spawn_entity:\n", self._source)


class TestActionNameIsLibraryScoped(unittest.TestCase):
    # pylint: disable=missing-function-docstring, protected-access

    def setUp(self) -> None:
        m._library_dist_by_file.cache_clear()

    def _with_libraries(self, mapping):
        """Pin the library-file -> distribution map the resolver consults."""
        self.addCleanup(setattr, m, "_library_dist_by_file", m._library_dist_by_file)
        m._library_dist_by_file = lambda: mapping

    def test_a_plugin_is_taken_from_the_package_whose_library_declared_the_action(self):
        """Two packages may each ship an action of the same name -- two simulator libraries both
        offering `spawn_entity` is the obvious case. The one that answers is the one whose library
        the scenario imported, which is what makes such a name usable at all."""
        self._with_libraries({"/pkg/one/lib_osc/sim_one.osc": "package_one",
                              "/pkg/two/lib_osc/sim_two.osc": "package_two"})
        plugins = [_Plugin("package_one"), _Plugin("package_two")]

        scoped = m._plugins_declaring(plugins, _Decl("/pkg/two/lib_osc/sim_two.osc"))
        self.assertEqual([p.dist.name for p in scoped], ["package_two"])

        scoped = m._plugins_declaring(plugins, _Decl("/pkg/one/lib_osc/sim_one.osc"))
        self.assertEqual([p.dist.name for p in scoped], ["package_one"])

    def test_a_declaration_that_is_not_a_librarys_disambiguates_nothing(self):
        """A scenario declaring its own action names no package, so the caller reports the
        ambiguity rather than binding an implementation the author never named."""
        self._with_libraries({"/pkg/one/lib_osc/sim_one.osc": "package_one"})
        plugins = [_Plugin("package_one"), _Plugin("package_two")]
        self.assertEqual(m._plugins_declaring(plugins, _Decl("/tmp/my_scenario.osc")), [])

    def test_a_declaration_with_no_source_disambiguates_nothing(self):
        self._with_libraries({})
        self.assertEqual(m._plugins_declaring([_Plugin("a")], _Decl("")), [])
