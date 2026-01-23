from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import os
import sys
import types
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Dict, Iterable, Optional, cast

from shared.utils import InvalidActionError, validate_action

from shared.types import ModAction, ModEvent, Noop

def alias_module(src: str, dst: str):
    """
    Make module `dst` behave like `src` for importers.
    Example: alias_module('sdk.quote_mod_sdk', 'quote_mod_sdk')
    """
    mod = importlib.import_module(src)
    sys.modules[dst] = mod

    # Mirror any submodules that are already loaded
    prefix = src + "."
    for name, submod in list(sys.modules.items()):
        if name.startswith(prefix):
            sys.modules[dst + name[len(src):]] = submod

    return mod

# Use it:
alias_module('sdk.quote_mod_sdk', 'quote_mod_sdk')

class ModPayloadError(ValueError):
    """Raised when a submitted mod payload is invalid."""


def _invalidate_module(prefix: str) -> None:
    """Remove a module and its submodules from sys.modules to force a clean import."""
    to_delete = [
        name
        for name in list(sys.modules.keys())
        if name == prefix or name.startswith(prefix + ".")
    ]
    for name in to_delete:
        try:
            del sys.modules[name]
        except Exception:
            pass


def _ensure_sys_path(paths: Iterable[str]) -> None:
    for p in paths:
        if not p:
            continue
        abspath = os.path.abspath(p)
        if abspath not in sys.path:
            sys.path.insert(0, abspath)


def _load_from_import_path(
    module_path: str, search_paths: Iterable[str]
) -> types.ModuleType:
    _ensure_sys_path(search_paths)
    importlib.invalidate_caches()
    _invalidate_module(module_path)
    try:
        return importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover - depends on environment
        raise ModPayloadError(
            f"Failed to import module '{module_path}' from {list(search_paths)}: {exc}"
        ) from exc


def load_mod_from_payload(
    payload: Dict[str, Any],
) -> Callable[[ModEvent, Optional[Any]], ModAction]:
    if not isinstance(payload, dict):
        raise ModPayloadError("Mod payload must be an object")
    language = payload.get("language")
    if language != "python":
        raise ModPayloadError("Only Python mods are supported in v0")

    # Path-based or multi-file registration
    module_name = payload.get("module")
    entrypoint = payload.get("entrypoint")
    use_dir = payload.get("dir")
    use_files = payload.get("files")
    source = payload.get("source")

    if not isinstance(entrypoint, str) or entrypoint.strip() == "":
        raise ModPayloadError("Mod payload is missing entrypoint")

    # Case 1: Multi-source inline bundle: {"source": {"path.py": "code", ...}}
    if isinstance(source, dict):
        src_map: Dict[str, str] = {}
        for k, v in source.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ModPayloadError("source mapping must be {str: str}")
            src_map[k] = v

        if not isinstance(module_name, str) or not module_name.strip():
            raise ModPayloadError(
                "Multi-source mods require 'module' to be the import path of the entry module (e.g., 'bundle.main')"
            )

        # Normalize path->module names
        def _to_module_name(path: str) -> str:
            p = path.replace("\\", "/").lstrip("./")
            if p.endswith("/__init__.py"):
                p = p[: -len("/__init__.py")]
            elif p.endswith(".py"):
                p = p[: -len(".py")]
            return p.replace("/", ".")

        module_sources: Dict[str, str] = {}
        package_names: set[str] = set()
        for path, code in src_map.items():
            mod_name = _to_module_name(path)
            if not mod_name:
                raise ModPayloadError(f"Invalid source path: {path}")
            # Track parent packages
            parts = mod_name.split(".")
            for i in range(1, len(parts)):
                package_names.add(".".join(parts[:i]))
            # If this is a package __init__.py, consider it a package with code
            if path.replace("\\", "/").endswith("/__init__.py"):
                package_names.add(mod_name)
            module_sources[mod_name] = code

        # In-memory finder/loader
        class _InMemoryFinder(importlib.abc.MetaPathFinder):  # type: ignore[attr-defined]
            def __init__(self, modules: Dict[str, str], packages: set[str]) -> None:
                self.modules = modules
                self.packages = set(packages)

            def find_spec(
                self,
                fullname: str,
                path: Optional[Iterable[str]] = None,
                target: Optional[types.ModuleType] = None,
            ):  # type: ignore[override]
                is_pkg = fullname in self.packages
                has_code = fullname in self.modules
                if not is_pkg and not has_code:
                    return None
                loader = _InMemoryLoader(self)
                spec = importlib.machinery.ModuleSpec(
                    fullname, loader, is_package=is_pkg
                )  # type: ignore[attr-defined]
                return spec

        class _InMemoryLoader(importlib.abc.Loader):  # type: ignore[attr-defined]
            def __init__(self, finder: _InMemoryFinder) -> None:
                self.finder = finder

            def create_module(self, spec):  # type: ignore[override]
                return None  # use default module creation

            def exec_module(self, module: types.ModuleType) -> None:  # type: ignore[override]
                fullname = module.__name__
                if fullname in self.finder.packages:
                    # Mark as a package
                    module.__package__ = fullname
                    if not hasattr(module, "__path__"):
                        module.__path__ = []  # type: ignore[attr-defined]
                # If we have code for this module (regular module or package __init__), execute it
                code = self.finder.modules.get(fullname)
                if code is not None:
                    pkg = fullname.rsplit(".", 1)[0] if "." in fullname else fullname
                    module.__package__ = pkg
                    exec(code, module.__dict__, module.__dict__)

        # Invalidate any existing modules for this bundle (top-level packages derived from sources)
        top_levels = {
            name.split(".")[0]
            for name in set(module_sources.keys()) | set(package_names)
        }
        for top in top_levels:
            _invalidate_module(top)

        finder = _InMemoryFinder(module_sources, package_names)
        sys.meta_path.insert(0, finder)
        try:
            module = importlib.import_module(module_name)
        finally:
            # Best-effort remove our finder to avoid hijacking unrelated imports
            try:
                sys.meta_path.remove(finder)
            except ValueError:
                pass

        candidate_obj = getattr(module, entrypoint, None)
        if not callable(candidate_obj):
            raise ModPayloadError(
                f"Entrypoint '{entrypoint}' not found or not callable in module '{module_name}'"
            )
        candidate = cast(Callable[..., ModAction | None], candidate_obj)

    # Case 2: Directory or file list pointing to importable module
    elif (isinstance(use_dir, str) and use_dir.strip()) or isinstance(use_files, list):
        if not isinstance(module_name, str) or not module_name.strip():
            raise ModPayloadError(
                "Path-based mods require 'module' to be the import path (e.g., 'examples.tau2.mod3')"
            )
        search_paths: list[str] = []
        if isinstance(use_dir, str) and use_dir.strip():
            root = Path(use_dir).resolve()
            if not root.is_dir():
                raise ModPayloadError(
                    f"dir does not exist or is not a directory: {use_dir}"
                )
            # Try to locate the package base such that base/module_path.py exists
            module_suffix = module_name.replace(".", os.sep) + ".py"
            found_base = None
            for cand in [root] + list(root.parents):
                if (cand / module_suffix).exists():
                    found_base = cand
                    break
            if found_base is None:
                # Fallback: use project root (cwd) and the provided dir
                search_paths.extend([str(root), os.getcwd()])
            else:
                search_paths.append(str(found_base))
        if isinstance(use_files, list) and use_files:
            try:
                file_paths = [Path(str(p)).resolve() for p in use_files]
                # Use lowest common ancestor as initial root
                common_root = os.path.commonpath([str(p) for p in file_paths])
                common_root_path = Path(common_root)
                module_suffix = module_name.replace(".", os.sep) + ".py"
                found_base = None
                for cand in [common_root_path] + list(common_root_path.parents):
                    if (cand / module_suffix).exists():
                        found_base = cand
                        break
                if found_base is None:
                    search_paths.extend([str(common_root_path), os.getcwd()])
                else:
                    search_paths.append(str(found_base))
            except Exception as exc:
                raise ModPayloadError(f"Invalid 'files' list: {exc}") from exc

        module = _load_from_import_path(module_name, search_paths)
        candidate_obj = getattr(module, entrypoint, None)
        if not callable(candidate_obj):
            raise ModPayloadError(
                f"Entrypoint '{entrypoint}' not found or not callable in module '{module_name}'"
            )
        candidate = cast(Callable[..., ModAction | None], candidate_obj)

    # Case 3: Single-source inline code (legacy)
    else:
        module_name = module_name or "client_mod"
        if not isinstance(source, str) or source.strip() == "":
            raise ModPayloadError("Mod payload is missing source")
        module = types.ModuleType(module_name)
        module.__package__ = None
        sys.modules[module_name] = module
        code_globals = module.__dict__
        try:
            exec(dedent(source), code_globals, code_globals)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            import traceback

            raise ModPayloadError(
                f"Mod failed to import: {exc}\n{traceback.format_exc()}"
            ) from exc

        candidate_obj = getattr(module, entrypoint, None)
        if not callable(candidate_obj):
            sys.modules.pop(module_name, None)
            raise ModPayloadError(f"Entrypoint '{entrypoint}' is not callable")
        candidate = cast(Callable[..., ModAction | None], candidate_obj)

    def _wrapped(event: ModEvent, tokenizer: Optional[Any] = None) -> ModAction:
        try:
            try:
                result = candidate(event, tokenizer)
            except TypeError:
                result = candidate(event)
        except Exception as exc:
            raise ModPayloadError(f"Mod raised exception: {exc}") from exc
        if result is None:
            return Noop()
        if not isinstance(result, ModAction):
            raise ModPayloadError(
                f"Mod returned unsupported type {type(result).__name__}; expected ModAction"
            )
        try:
            return validate_action(event, result)
        except InvalidActionError as exc:
            raise ModPayloadError(str(exc)) from exc

    _wrapped.__name__ = f"{entrypoint}"
    return _wrapped


__all__ = ["load_mod_from_payload", "ModPayloadError"]
