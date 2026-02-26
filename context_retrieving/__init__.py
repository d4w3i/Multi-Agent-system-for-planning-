"""
Context Retrieving Package

Modules for analysing Python repositories and generating AI-ready context.

Components:
- CallGraphBuilder: Builds the function call graph
- ContextGenerator: Generates AI-ready context files for functions
- TreeGenerator: Generates an ASCII representation of a directory structure
- BatchContextRetriever: Processes batches of projects for context retrieval
"""

from .call_graph_builder import CallGraphBuilder
from .context_generator import ContextGenerator
from .generate_tree import TreeGenerator
from .batch_context_retriever import BatchContextRetriever

__all__ = [
    'CallGraphBuilder',
    'ContextGenerator',
    'TreeGenerator',
    'BatchContextRetriever'
]
