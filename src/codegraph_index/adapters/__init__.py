"""Language-specific extraction adapters."""

from codegraph_index.adapters.cpp import CppExtractionAdapter
from codegraph_index.adapters.python import PythonExtractionAdapter

__all__ = ["CppExtractionAdapter", "PythonExtractionAdapter"]
