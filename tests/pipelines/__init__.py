"""Pipeline tests — end-to-end agent integration tests.

These tests require a running Neo4j instance and an LLM backend
(LLM_API_KEY in .env).  They are decorated with ``@pytest.mark.slow``
and excluded from fast test runs.

Run selectively::

    pytest tests/pipelines/ -m slow
"""


