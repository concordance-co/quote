"""Custom setuptools build hooks for the quote package."""

from __future__ import annotations

from setuptools.command.build_py import build_py as _build_py


class SkipRemoteBuildPy(_build_py):
    """Skip packaging the remote backend module when building the wheel."""

    _SKIP_PACKAGE = "quote.server.openai"
    _SKIP_MODULE = "remote"

    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        filtered = [
            (pkg, mod, module_file)
            for pkg, mod, module_file in modules
            if not (pkg == self._SKIP_PACKAGE and mod == self._SKIP_MODULE)
        ]
        if len(filtered) != len(modules):
            self.announce(
                f"Skipping module {self._SKIP_PACKAGE}.{self._SKIP_MODULE} during module discovery",
                level=2,
            )
        return filtered

    def build_module(self, module, module_file, package):
        if package == self._SKIP_PACKAGE and module == self._SKIP_MODULE:
            self.announce(
                f"Skipping module {package}.{module} during build",
                level=2,
            )
            return
        return super().build_module(module, module_file, package)
