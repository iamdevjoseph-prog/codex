"""
skill_loader — Loads skills from hyphenated directory names into importable modules.

Skill directories use hyphens (seo-engine/) for display clarity, but Python
requires underscores for package imports. This loader bridges the gap by
reading files directly and registering them in sys.modules under underscore
aliases, so both `skill_loader.run("seo-engine", ...)` and
`from core.skills.seo_engine.main import run` work without renaming directories.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Callable

_SKILLS_DIR = Path(__file__).parent / "skills"
_MODULE_CACHE: dict[str, types.ModuleType] = {}


def load(name: str) -> types.ModuleType:
    """
    Load a skill module by its hyphenated name (e.g. 'trailofbits-security').
    Caches the module after first load.
    """
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]

    main_file = _SKILLS_DIR / name / "main.py"
    if not main_file.exists():
        raise ImportError(f"Skill '{name}' not found — expected {main_file}")

    module_key = f"__skill_{name.replace('-', '_')}__"
    spec = importlib.util.spec_from_file_location(module_key, main_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module
    spec.loader.exec_module(module)

    _MODULE_CACHE[name] = module
    return module


def get_fn(name: str) -> Callable:
    """Return the callable entry point (run or invoke) for a skill."""
    module = load(name)
    fn = getattr(module, "run", None) or getattr(module, "invoke", None)
    if fn is None:
        raise AttributeError(f"Skill '{name}' exposes neither run() nor invoke()")
    return fn


def run(name: str, input: dict[str, Any]) -> dict[str, Any]:
    """Load and invoke a skill in one call."""
    return get_fn(name)(input)


def register_all_as_python_packages() -> None:
    """
    Register every skill in sys.modules under its underscore-aliased package path
    so that `from core.skills.trailofbits_security.main import run` resolves
    even though the filesystem directory uses a hyphen.
    """
    if not _SKILLS_DIR.exists():
        return

    for skill_dir in _SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        py_name = skill_name.replace("-", "_")

        main_file = skill_dir / "main.py"
        if not main_file.exists():
            continue

        pkg_key = f"core.skills.{py_name}"
        mod_key = f"core.skills.{py_name}.main"

        if mod_key in sys.modules:
            continue

        spec = importlib.util.spec_from_file_location(mod_key, main_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_key] = module
        spec.loader.exec_module(module)

        # Create a stub package node so the dotted path resolves
        if pkg_key not in sys.modules:
            pkg = types.ModuleType(pkg_key)
            pkg.__path__ = [str(skill_dir)]
            pkg.main = module
            sys.modules[pkg_key] = pkg

        _MODULE_CACHE[skill_name] = module
