"""Custom setuptools build hooks for the quote package."""

from __future__ import annotations

from setuptools.command.build_py import build_py as _build_py


class SkipRemoteBuildPy(_build_py):
    """Skip packaging the remote backend module when building the wheel."""

    _SKIP_TARGETS = {
        ("quote.api.openai", "remote"),
        ("quote.server.openai", "remote"),
    }

    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        filtered = [
            (pkg, mod, module_file)
            for pkg, mod, module_file in modules
            if (pkg, mod) not in self._SKIP_TARGETS
        ]
        if len(filtered) != len(modules):
            skipped = ", ".join(f"{pkg}.{mod}" for pkg, mod in sorted(self._SKIP_TARGETS))
            self.announce(
                f"Skipping module(s) {skipped} during module discovery",
                level=2,
            )
        return filtered

    def build_module(self, module, module_file, package):
        if (package, module) in self._SKIP_TARGETS:
            self.announce(
                f"Skipping module {package}.{module} during build",
                level=2,
            )
            return
        return super().build_module(module, module_file, package)
