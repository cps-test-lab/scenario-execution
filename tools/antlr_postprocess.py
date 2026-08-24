# Copyright (C) 2025 Frederik Pasch
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

"""Re-apply the edits ANTLR does not emit, so regenerated parser files match the tree.

ANTLR overwrites its output wholesale, so each of these has to be re-applied after every
regeneration. Doing it by hand is how they get lost: none of them is visible until
something downstream breaks, and the last two were only discovered by diffing a
regeneration against the committed files.

Run via `make parser`, not directly.
"""

import sys

LICENSE_HEADER = """# Copyright (C) 2024 Intel Corporation
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

"""

# The lexer target emits this import unconditionally, and typing.io is deprecated since
# 3.8 and removed in 3.13. The parser target emits a `sys.version_info` guard around the
# same import instead, which resolves to `typing` on every supported version -- so it is
# correct as generated and must be left alone. Anchoring on the following `import sys`
# keeps this replacement away from the guarded (tab-indented) form.
TYPING_IO_IMPORT = "from typing.io import TextIO\nimport sys\n"
TYPING_IMPORT = "import sys\nfrom typing import TextIO\n"


def postprocess(path):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    original = text

    if "SPDX-License-Identifier" not in text:
        text = LICENSE_HEADER + text
    text = text.replace(TYPING_IO_IMPORT, TYPING_IMPORT)
    if not text.endswith("\n"):
        text += "\n"

    if text != original:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return text != original


def main():
    if len(sys.argv) < 2:
        print("usage: antlr_postprocess.py <generated.py>...", file=sys.stderr)
        return 1
    for path in sys.argv[1:]:
        changed = postprocess(path)
        print(f"  {'patched ' if changed else 'unchanged'} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
