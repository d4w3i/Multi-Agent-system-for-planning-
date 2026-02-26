"""
=============================================================================
_AST_VISITORS.PY - AST Traversal Mixin for CallGraphBuilder
=============================================================================

This module defines _ASTVisitorMixin, a mixin class that holds the six
private AST traversal methods extracted from CallGraphBuilder.

Splitting these methods into a dedicated mixin keeps call_graph_builder.py
focused on orchestration logic (4-pass pipeline, I/O, graph export) while
this file owns the Tree-sitter traversal details.

ATTRIBUTES EXPECTED FROM THE HOST CLASS (CallGraphBuilder.__init__):
    call_graph          defaultdict   The main function graph
    all_functions       set           All fully-qualified function names
    all_classes         set           All fully-qualified class names
    import_map          dict          {filepath: {alias: full_name}}
    verbose             bool          Debug output flag
    repo_root           Path | None   Repository root for module path calc
    _suffix_index       dict          {short_name: [full_names]}
    _suffix_index_stale bool          True when index needs rebuilding

=============================================================================
"""

import logging

from shared.tree_sitter_utils import get_node_text

logger = logging.getLogger(__name__)


# =============================================================================
# MIXIN _ASTVisitorMixin - AST Traversal Methods

class _ASTVisitorMixin:
    """
    Mixin providing the six private AST traversal methods used by
    CallGraphBuilder.  Must be mixed in before object (MRO order):

        class CallGraphBuilder(_ASTVisitorMixin):
            ...

    All attributes accessed via self are defined in CallGraphBuilder.__init__.
    """

    # =========================================================================
    # METHOD _rebuild_suffix_index - Rebuild Suffix Index

    def _rebuild_suffix_index(self):
        """Rebuild the suffix index for O(1) partial name lookups."""
        self._suffix_index = {}
        for fn in self.all_functions:
            short_name = fn.rsplit('.', 1)[-1]
            self._suffix_index.setdefault(short_name, []).append(fn)
        self._suffix_index_stale = False

    # =========================================================================
    # METHOD _extract_imports - Import Statement Extraction

    def _extract_imports(self, node, code_bytes: bytes, filepath: str, import_map: dict = None):
        """
        Extract all import statements and build a resolution map.

        Python imports can have different forms, and this method
        handles them all to build an alias → full_name map.

        HANDLED IMPORT FORMS:

        1. import module
           E.g.: import os
           Map: {"os": "os"}

        2. import module as alias
           E.g.: import pandas as pd
           Map: {"pd": "pandas"}

        3. from module import name
           E.g.: from os.path import join
           Map: {"join": "os.path.join"}

        4. from module import name as alias
           E.g.: from pandas import DataFrame as DF
           Map: {"DF": "pandas.DataFrame"}

        5. from module import *
           E.g.: from utils import *
           Map: {"*": "utils"}  # Cannot resolve precisely

        TREE-SITTER AST STRUCTURE:

        import_statement
        ├── dotted_name ("os")
        └── aliased_import
            ├── name: dotted_name
            └── alias: identifier

        import_from_statement
        ├── module_name: dotted_name ("os.path")
        └── [various children for what's imported]

        Args:
            node: Current AST node
            code_bytes (bytes): File content
            filepath (str): File path (for logging)
            import_map (dict): Map to populate (created if None)

        Returns:
            dict: The map {alias: full_name}

        Example:
            # For a file with:
            # import pandas as pd
            # from collections import defaultdict

            # Returns:
            # {"pd": "pandas", "defaultdict": "collections.defaultdict"}
        """

        # Initialize map if not provided
        if import_map is None:
            import_map = {}

        # ---------------------------------------------------------------------
        # Case 1: import statement (import foo, import foo as bar)

        if node.type == 'import_statement':
            for child in node.children:

                # import module (without alias)
                if child.type == 'dotted_name':
                    module = get_node_text(child, code_bytes)
                    # Map the last part of the name to the full name
                    import_map[module.split('.')[-1]] = module

                # import module as alias
                elif child.type == 'aliased_import':
                    # Extract name and alias from node fields
                    name_node = child.child_by_field_name('name')
                    alias_node = child.child_by_field_name('alias')

                    if name_node and alias_node:
                        full_name = get_node_text(name_node, code_bytes)
                        alias = get_node_text(alias_node, code_bytes)
                        import_map[alias] = full_name

        # ---------------------------------------------------------------------
        # Case 2: from ... import statement

        elif node.type == 'import_from_statement':
            # Extract the module name from which we import
            module_node = node.child_by_field_name('module_name')

            if module_node:
                module = get_node_text(module_node, code_bytes)

                # Iterate over children to find what's imported
                for child in node.children:

                    # from module import name (without alias)
                    if child.type == 'dotted_name' and child != module_node:
                        name = get_node_text(child, code_bytes)
                        import_map[name] = f"{module}.{name}"

                    # from module import name as alias
                    elif child.type == 'aliased_import':
                        name_node = child.child_by_field_name('name')
                        alias_node = child.child_by_field_name('alias')

                        if name_node and alias_node:
                            name = get_node_text(name_node, code_bytes)
                            alias = get_node_text(alias_node, code_bytes)
                            import_map[alias] = f"{module}.{name}"

                    # from module import * (wildcard)
                    elif child.type == 'wildcard_import':
                        # Cannot know what's imported, so register only
                        # the module with a special key
                        import_map['*'] = module

        # ---------------------------------------------------------------------
        # Recursion on children

        # Continue searching for imports in all children of the node
        for child in node.children:
            self._extract_imports(child, code_bytes, filepath, import_map)

        return import_map

    # =========================================================================
    # METHOD _resolve_function_call - Function Name Resolution

    def _resolve_function_call(self, func_name: str, filepath: str, current_class: str | None = None) -> str | None:
        """
        Resolve a function name to its fully-qualified name.

        When we find a call like "process(data)", we need to understand
        WHICH function "process" is being called. It could be:
        - An imported function
        - A method of the current class
        - A function in the same module
        - A function from somewhere else

        RESOLUTION STRATEGY (in priority order):

        1. IMPORT MAP: Check if the name is an import in the current file
           E.g.: "pd.read_csv" where pd = pandas

        2. CURRENT CLASS: If we're in a class, try ClassName.method
           E.g.: in MyClass, "helper()" → "module.MyClass.helper"

        3. LOCAL MODULE: Try as function in the same module
           E.g.: in utils.py, "helper()" → "utils.helper"

        4. GLOBAL FALLBACK: Search among all known functions
           Useful for functions with unique names

        5. PARTIAL MATCH: Search for functions ending with .name
           E.g.: "process" matches "utils.process"

        Args:
            func_name (str): Function name to resolve
            filepath (str): File where the call appears
            current_class (str | None): Name of the current class

        Returns:
            str | None: Fully-qualified name, or None if not found

        Examples:
            # With import: import utils
            _resolve_function_call("helper", "main.py")
            # Might return: "utils.helper"

            # In a class
            _resolve_function_call("process", "main.py", current_class="MyClass")
            # Might return: "main.MyClass.process"
        """

        # 5-level fallback: import map → class method → local module → global → partial match
        # Each level is tried in order; first match wins.

        # ---------------------------------------------------------------------
        # STRATEGY 1: Check import map
        if filepath in self.import_map:
            if func_name in self.import_map[filepath]:
                resolved = self.import_map[filepath][func_name]

                # Verify that the resolved function exists in the graph
                if resolved in self.all_functions:
                    return resolved

                # Could be a module; try adding the name
                # E.g.: "pd" → "pandas", but we're looking for "pandas.func_name"
                candidate = f"{resolved}.{func_name}"
                if candidate in self.all_functions:
                    return candidate

        # ---------------------------------------------------------------------
        # STRATEGY 2: Try with current class
        if current_class:
            candidate = f"{self._get_module_path(filepath)}.{current_class}.{func_name}"
            if candidate in self.all_functions:
                return candidate

        # ---------------------------------------------------------------------
        # STRATEGY 3: Try local function in the same module
        module = self._get_module_path(filepath)
        candidate = f"{module}.{func_name}"
        if candidate in self.all_functions:
            return candidate

        # ---------------------------------------------------------------------
        # STRATEGY 4: Global fallback
        # For backward compatibility, search for the simple name
        if func_name in self.all_functions:
            return func_name

        # ---------------------------------------------------------------------
        # STRATEGY 5: Partial match using suffix index
        # Uses _suffix_index for O(1) lookup instead of O(n) scan
        if not hasattr(self, '_suffix_index') or self._suffix_index_stale:
            self._rebuild_suffix_index()
        matches = self._suffix_index.get(func_name, [])
        if len(matches) == 1:
            return matches[0]

        # No resolution found (or ambiguous match)
        return None

    # =========================================================================
    # METHOD _extract_functions - Function Definition Extraction
    # NOTE: Similar to evaluation/function_matcher.py:_extract_functions_recursive,
    # but populates the call graph data model. Not merged intentionally.

    def _extract_functions(self, node, code_bytes: bytes, filepath: str, current_class: str | None = None):
        """
        Extract function and method definitions from the AST.

        This method recursively traverses the AST looking for:
        - class_definition: to track the class context
        - function_definition: to extract functions and methods

        CLASS HANDLING:
        When we enter a class_definition, we pass the class name
        as current_class to children. This allows distinguishing:
        - Standalone functions: "module.function"
        - Class methods: "module.Class.method"

        AST STRUCTURE:

        class_definition
        ├── name: identifier ("MyClass")
        └── body: block
            └── function_definition
                ├── name: identifier ("my_method")
                └── body: block

        function_definition
        ├── name: identifier ("my_function")
        ├── parameters: parameters
        └── body: block

        INFORMATION EXTRACTED FOR EACH FUNCTION:
        - file: file path
        - line: line number (1-based, start_point[0] + 1)
        - code: complete source code
        - class_name: container class (if method)
        - is_method: True if it's a method
        - full_name: fully qualified name (module.class.function)

        Args:
            node: Current AST node
            code_bytes (bytes): File content
            filepath (str): File path
            current_class (str | None): Name of the current class

        Note:
            This method modifies self.call_graph and self.all_functions
        """

        # ---------------------------------------------------------------------
        # Handle class_definition
        if node.type == 'class_definition':
            # Extract the class name
            class_name_node = node.child_by_field_name('name')

            if class_name_node:
                class_name = code_bytes[class_name_node.start_byte:class_name_node.end_byte].decode('utf-8', errors='replace')

                # Build the fully qualified class name
                module_path = self._get_module_path(filepath)
                full_class_name = f"{module_path}.{class_name}"

                # Add to the set of classes (to resolve constructors)
                self.all_classes.add(full_class_name)

                # Recurse on class children, passing the class name
                # For nested classes, propagate the outer class context
                nested_class = f"{current_class}.{class_name}" if current_class else class_name
                for child in node.children:
                    self._extract_functions(child, code_bytes, filepath, current_class=nested_class)

                return

        # ---------------------------------------------------------------------
        # Handle function_definition
        if node.type == 'function_definition':
            # Extract the function name
            func_name_node = node.child_by_field_name('name')

            if func_name_node:
                # Function name
                func_name = code_bytes[func_name_node.start_byte:func_name_node.end_byte].decode('utf-8', errors='replace')

                # Complete source code of the function
                func_code = code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

                # Build the fully qualified name
                module_path = self._get_module_path(filepath)

                if current_class:
                    # It's a method: module.Class.method
                    full_name = f"{module_path}.{current_class}.{func_name}"
                    is_method = True
                else:
                    # It's a standalone function: module.function
                    full_name = f"{module_path}.{func_name}"
                    is_method = False

                # Register the function
                self.all_functions.add(full_name)
                self._suffix_index_stale = True

                # Populate call_graph with metadata
                self.call_graph[full_name]['file'] = filepath
                self.call_graph[full_name]['line'] = node.start_point[0] + 1  # 1-based
                self.call_graph[full_name]['code'] = func_code
                self.call_graph[full_name]['class_name'] = current_class
                self.call_graph[full_name]['is_method'] = is_method
                self.call_graph[full_name]['full_name'] = full_name

                logger.debug("Found: %s in %s", full_name, filepath)

        # ---------------------------------------------------------------------
        # Recurse on children (if not in a class_definition)
        # The class_definition is already handled above with return
        if node.type != 'class_definition':
            for child in node.children:
                self._extract_functions(child, code_bytes, filepath, current_class)

    # =========================================================================
    # METHOD _extract_calls - Function Call Extraction

    def _extract_calls(self, node, code_bytes: bytes, filepath: str, current_class: str | None = None):
        """
        Extract function calls from the AST and add them to the call graph.

        This method is similar to _extract_functions but looks for "call"
        nodes instead of definitions.

        HANDLED CALL TYPES:

        1. Direct call: func()
           AST: call → function: identifier

        2. Constructor call: MyClass()
           Mapped to MyClass.__init__()

        3. Method call via self: self.method()
           AST: call → function: attribute (object="self", attribute="method")

        4. Method call via object: obj.method()
           AST: call → function: attribute (object="obj", attribute="method")

        LOGIC:
        1. Find the 'call' node
        2. Extract the 'function' node (who is being called)
        3. Determine the call type (direct, method, etc.)
        4. Resolve the fully qualified name using _resolve_function_call
        5. Update call_graph['calls'] and call_graph['called_by']

        Args:
            node: Current AST node
            code_bytes (bytes): File content
            filepath (str): File path
            current_class (str | None): Current class (to resolve self)

        Note:
            This method modifies self.call_graph (calls and called_by)
        """

        # ---------------------------------------------------------------------
        # Track class context
        if node.type == 'class_definition':
            class_name_node = node.child_by_field_name('name')
            if class_name_node:
                class_name = code_bytes[class_name_node.start_byte:class_name_node.end_byte].decode('utf-8', errors='replace')

                # Recurse with the new class context
                for child in node.children:
                    self._extract_calls(child, code_bytes, filepath, current_class=class_name)
                return

        # ---------------------------------------------------------------------
        # Find the containing function
        # We need to know IN WHICH function we are to register: "who calls whom"
        current_function = self._get_parent_function(node, code_bytes, filepath, current_class)

        # ---------------------------------------------------------------------
        # Handle 'call' node (function call)
        if node.type == 'call':
            # The 'function' field contains who is being called
            func_node = node.child_by_field_name('function')

            if func_node:
                called_func = None  # Resolved name of the called function
                # -----------------------------------------------------------------
                # CASE 1: Direct call - func() or ClassName()
                if func_node.type == 'identifier':
                    func_name = get_node_text(func_node, code_bytes)

                    # Check if it's a constructor call
                    # E.g.: MyClass() → MyClass.__init__()
                    for full_class_name in self.all_classes:
                        if full_class_name.endswith(f".{func_name}") or full_class_name == func_name:
                            constructor = f"{full_class_name}.__init__"
                            if constructor in self.all_functions:
                                called_func = constructor
                                break

                    # If not a constructor, resolve normally
                    if not called_func:
                        called_func = self._resolve_function_call(func_name, filepath, current_class)

                # -----------------------------------------------------------------
                # CASE 2: Method call - self.method() or obj.method()
                elif func_node.type == 'attribute':
                    # Extract object and attribute
                    # E.g.: self.process → object="self", attribute="process"
                    object_node = func_node.child_by_field_name('object')
                    attribute_node = func_node.child_by_field_name('attribute')

                    if object_node and attribute_node:
                        obj_name = get_node_text(object_node, code_bytes)
                        method_name = get_node_text(attribute_node, code_bytes)

                        # Case self.method()
                        if obj_name == 'self' and current_class:
                            module_path = self._get_module_path(filepath)
                            called_func = f"{module_path}.{current_class}.{method_name}"

                            # Verify the method exists
                            if called_func not in self.all_functions:
                                called_func = None

                        # Try to resolve obj.method as import
                        if not called_func:
                            qualified_call = f"{obj_name}.{method_name}"
                            called_func = self._resolve_function_call(qualified_call, filepath, current_class)

                        # Fallback: search only the method name
                        if not called_func:
                            called_func = self._resolve_function_call(method_name, filepath, current_class)

                # -----------------------------------------------------------------
                # Update the call graph
                if called_func and current_function:
                    # Only update existing entries to avoid phantom entries in defaultdict
                    if current_function in self.call_graph:
                        if called_func not in self.call_graph[current_function]['calls']:
                            self.call_graph[current_function]['calls'].append(called_func)

                    if called_func in self.call_graph:
                        if current_function not in self.call_graph[called_func]['called_by']:
                            self.call_graph[called_func]['called_by'].append(current_function)

        # ---------------------------------------------------------------------
        # Recurse on children
        if node.type != 'class_definition':
            for child in node.children:
                self._extract_calls(child, code_bytes, filepath, current_class)

    # =========================================================================
    # METHOD _get_parent_function - Find the Containing Function

    def _get_parent_function(self, node, code_bytes: bytes, filepath: str, current_class: str | None = None):
        """
        Find the function that contains a given AST node.

        When we find a function call, we need to know IN WHICH
        function it's located to build the call graph edge.

        ALGORITHM:
        1. Start from the current node
        2. Climb up the tree (node.parent) until finding function_definition
        3. Extract the name and build the fully qualified name

        Args:
            node: Starting AST node
            code_bytes (bytes): File content
            filepath (str): File path
            current_class (str | None): Current class

        Returns:
            str | None: Fully qualified name of the containing function, or None if
                 the node is not inside a function (e.g., top-level code)

        Example:
            # If node is inside:
            # def my_func():
            #     x = other_func()  ← node is here

            # Returns: "module.my_func"
        """

        # Climb up the tree looking for function_definition
        current = node.parent

        while current:
            if current.type == 'function_definition':
                # Found the containing function
                func_name_node = current.child_by_field_name('name')

                if func_name_node:
                    func_name = code_bytes[func_name_node.start_byte:func_name_node.end_byte].decode('utf-8', errors='replace')
                    module_path = self._get_module_path(filepath)

                    # Build the fully qualified name
                    if current_class:
                        return f"{module_path}.{current_class}.{func_name}"
                    return f"{module_path}.{func_name}"

            # Continue climbing
            current = current.parent

        # Not inside any function (top-level code)
        return None
