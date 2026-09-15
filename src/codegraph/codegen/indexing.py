"""In-process indexing helpers for code-generation round trips."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from codegraph_index import IndexMode, IndexRequest, IndexResult, index


def index_generated_tree(
    project_root: str | Path,
    *,
    project_id: str,
    repository_id: str,
    source: str,
    input_paths: Sequence[str | Path] | None = None,
    test_paths: Sequence[str | Path] = (),
    output_dir: str | Path | None = None,
    file_patterns: Sequence[str] = (),
    exclude_patterns: Sequence[str] = (),
    predefined: Sequence[str] = (),
    adapter_options: dict | None = None,
) -> IndexResult:
    """Parse generated C++ in-process without persisting it.

    Codegen round trips need the extracted graph for verification, but must
    not mutate the caller's configured graph. The helper makes that policy
    explicit by always using :attr:`IndexMode.EXTRACT_ONLY`; Doxygen remains
    an implementation detail of the C++ extraction adapter.
    """
    root = Path(project_root).resolve()
    paths = tuple(Path(path) for path in (input_paths or (root,)))
    request = IndexRequest(
        project_root=root,
        project_id=project_id,
        repository_id=repository_id,
        source=source,
        language="cpp",
        input_paths=paths,
        test_paths=tuple(Path(path) for path in test_paths),
        output_dir=Path(output_dir) if output_dir is not None else None,
        file_patterns=tuple(file_patterns),
        exclude_patterns=tuple(exclude_patterns),
        predefined=tuple(predefined),
        mode=IndexMode.EXTRACT_ONLY,
        adapter_options=adapter_options or {},
    )
    return index(request)


__all__ = ["index_generated_tree"]
