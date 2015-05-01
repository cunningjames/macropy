"""Plumbing related to hooking into the import process, unrelated to MacroPy"""


import ast
import imp
import sys
import traceback

from six import PY3

import macropy.core.macros
import macropy.core.util
import macropy.activate


if macropy.core.macros.PY3:
    from importlib.machinery import PathFinder
    from types import ModuleType


class _MacroLoader(object):
    """Performs the loading of a module with macro expansion."""
    def __init__(self, module_name, mod):
        self.mod = mod
        sys.sys.modules[module_name] = mod

    def load_module(self, fullname):
        return self.mod


@macropy.core.util.singleton
class MacroFinder(object):
    """Loads a module and looks for macros inside, only providing a loader if
    it finds some."""
    def expand_macros(self, source_code, filename):
        """ Parses the source_code and expands the resulting ast. 
        Returns both the compiled ast and new ast. 
        If no macros are found, returns None, None."""

        if not source_code or "macros" not in source_code:
            return None, None
        tree = ast.parse(source_code)
        bindings = macropy.core.macros.detect_macros(tree)

        if not bindings: 
            return None, None

        for (p, _) in bindings:
            __import__(p)

        modules = [(sys.modules[p], bind) for (p, bind) in bindings]
        new_tree = macropy.core.macros.expand_entire_ast(tree, source_code, modules)
        return compile(tree, filename, "exec"), new_tree

    def construct_module(self, module_name, file_path):
        if macropy.core.macros.PY3:
            mod = ModuleType(module_name)
        else:
            mod = imp.imp.new_module(module_name)
        mod.__package__ = module_name.rpartition('.')[0]
        mod.__file__ = file_path
        mod.__loader__ = _MacroLoader(module_name, mod)
        return mod

    def export(self, code, tree, module_name, file_path):
        try:
            macropy.exporter.export_transformed(
                code, tree, module_name, file_path)
        except: pass 

    def get_source(self, module_name, package_path):
        if macropy.core.macros.PY3:
            # try to get the module using a "normal" loader.
            # if we fail here, just let python handle the rest
            original_loader = (PathFinder.find_module(module_name, package_path))
            source_code = original_loader.get_source(module_name)
            file_path = original_loader.path
        else:
            (file, pathname, description) = imp.imp.find_module(
                module_name.split('.')[-1],
                package_path
            )
            source_code = file.read()
            file.close()
            file_path = file.name
        return source_code, file_path

    def find_module(self, module_name, package_path):
        try:
            source_code, file_path = self.get_source(module_name, package_path)
        except:
            return
        try:
            # try to find already exported module
            # TODO: are these the right arguments?
            module = macropy.exporter.find(
                file_path, file_path, "", module_name, package_path)
            if module:
                return _MacroLoader(ast.mod)
            code, tree = self.expand_macros(source_code, file_path)
            if not code: # no macros!
                return
            module = self.construct_module(module_name, file_path)
            exec(code, module.__dict__)
            self.export(code, tree, module_name, file_path)
            return module.__loader__
        except Exception as e:
            print("import_hooks.MacroFinder raised", e)
            traceback.print_exc()
