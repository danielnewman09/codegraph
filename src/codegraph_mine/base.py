"""Abstract base for LLM-based requirement mining from codegraph nodes.

Follows the same template-method pattern as
:class:`codegraph_enrich.base.GraphEnricher` but creates new nodes
(HLRs, LLRs) and relationships rather than updating existing fields.

Subclasses must implement:

* ``system_prompt`` — property returning the LLM system prompt
* ``_find_targets(**filters)`` — query Neo4j for all eligible parent
  nodes (e.g. compounds with tests)
* ``_fetch_context(target)`` — fetch all test context for one target
* ``_build_prompt(target, context)`` — build the batch user prompt
* ``_create_llm_output_schema()`` — return the Pydantic model for
  structured LLM output

The base class handles:

* ``_call_llm()`` — delegates to ``llm_caller.call_structured()``
  (structured output via Pydantic schema)
* ``enrich_one()`` — template method: fetch → prompt → call → parse →
  persist
* ``enrich_all()`` — template method: find targets → enrich_one loop
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from codegraph_mine.schemas import MinedRequirements

log = logging.getLogger(__name__)

# Bound type variable for the LLM output schema
S = TypeVar("S", bound=BaseModel)


# ══════════════════════════════════════════════════════════════════════════
# Result types
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class MineResult:
    """Result of mining requirements from a single compound.

    Attributes:
        compound_name: The compound's fully-qualified name.
        hlr_description: The inferred HLR description.
        llr_count: Number of LLRs created.
        test_count: Number of tests linked to LLRs.
        error: Error message if mining failed.
        skipped: Whether this compound was skipped.
        skip_reason: Why this compound was skipped.
    """

    compound_name: str
    hlr_description: str = ""
    llr_count: int = 0
    test_count: int = 0
    error: str | None = None
    skipped: bool = False
    skip_reason: str = ""

    @property
    def success(self) -> bool:
        """True if mining succeeded and at least one LLR was created."""
        return self.llr_count > 0 and self.error is None

    def to_dict(self) -> dict:
        return {
            "compound_name": self.compound_name,
            "hlr_description": self.hlr_description,
            "llr_count": self.llr_count,
            "test_count": self.test_count,
            "success": self.success,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "error": self.error,
        }


@dataclass
class MineSummary:
    """Summary of a mining run across all compounds.

    Attributes:
        results: Per-compound :class:`MineResult` objects.
        errors: Non-compound-specific error messages.
        total_compounds: Total compounds processed.
        total_skipped: How many were skipped.
        total_errors: How many failed.
        total_llrs: Total LLRs created.
        total_tests_linked: Total test→LLR links created.
    """

    results: list[MineResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_compounds: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    total_llrs: int = 0
    total_tests_linked: int = 0

    def to_dict(self) -> dict:
        return {
            "total_compounds": self.total_compounds,
            "total_skipped": self.total_skipped,
            "total_errors": self.total_errors,
            "total_llrs": self.total_llrs,
            "total_tests_linked": self.total_tests_linked,
            "results": [r.to_dict() for r in self.results],
            "errors": self.errors,
        }


# ══════════════════════════════════════════════════════════════════════════
# RequirementMiner — abstract template-method base
# ══════════════════════════════════════════════════════════════════════════


class RequirementMiner(ABC):
    """Abstract base for LLM-based requirement mining.

    Subclasses define **what** to mine (which Neo4j nodes, what
    context to fetch, how to build prompts) while the base class
    handles **how** (the fetch → prompt → call → parse → persist
    pipeline, LLM calling, JSON parsing).

    To create a new miner, subclass and implement:

    * :meth:`system_prompt`
    * :meth:`_find_targets`
    * :meth:`_fetch_context`
    * :meth:`_build_prompt`
    * :meth:`_persist_results`

    Optionally override :meth:`_should_mine_target` (default: requires
    at least one test).

    Args:
        log_dir: Optional directory for prompt + response trace logs.
        disable_thinking: Suppress LLM thinking output.
    """

    def __init__(
        self,
        log_dir: str | None = None,
        disable_thinking: bool = True,
    ):
        self.log_dir = Path(log_dir) if log_dir else None
        self.disable_thinking = disable_thinking

    # ------------------------------------------------------------------
    # Concrete utilities (shared across all miners)
    # ------------------------------------------------------------------

    @staticmethod
    def node_name(node) -> str:
        """Best-effort readable name from a neomodel node."""
        return (
            getattr(node, "qualified_name", "")
            or getattr(node, "name", "?")
        )

    @staticmethod
    def parse_llm_response(response: str) -> dict[str, Any]:
        """Parse an LLM batch response into a JSON dict.

        Handles markdown code fences and leading/trailing text around
        the JSON object.
        """
        text = response.strip()

        # Strip markdown code fences
        fence_match = re.match(
            r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL
        )
        if fence_match:
            text = fence_match.group(1).strip()

        brace_start = text.find("{")
        if brace_start == -1:
            raise ValueError(
                f"No JSON object found in response: {text[:200]}"
            )

        brace_end = text.rfind("}")
        if brace_end == -1 or brace_end <= brace_start:
            raise ValueError(
                f"Malformed JSON in response: {text[:200]}"
            )

        try:
            result = json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to parse response JSON: {exc}"
                f"\nResponse: {text[:300]}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError(
                f"Response is not a JSON object: "
                f"{type(result).__name__}"
            )

        return result

    def _call_llm(
        self,
        system: str,
        user: str,
        *,
        model: str = "",
        max_tokens: int = 32768,
        call_label: str = "",
    ) -> str:
        """Call the LLM for text completion via ``llm_caller.call_text()``.

        Args:
            system: System prompt.
            user: User message / prompt.
            model: Model override.
            max_tokens: Maximum tokens in the response.
            call_label: Short identifier for the log filename.

        Returns:
            The LLM's text response (stripped).

        Raises:
            RuntimeError: If the call fails.
        """
        from llm_caller import call_text

        prompt_log_file = ""
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            label = (
                call_label.replace("::", "_").replace(".", "_")[:80]
                if call_label
                else "mine"
            )
            prompt_log_file = str(self.log_dir / f"{label}_{ts}.md")

        try:
            result = call_text(
                system=system,
                messages=[{"role": "user", "content": user}],
                model=model,
                max_tokens=max_tokens,
                disable_thinking=self.disable_thinking,
                prompt_log_file=prompt_log_file,
            )
            return result.strip()
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Abstract interface (subclass must implement)
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The system prompt sent to the LLM for every call.

        Should include role description, output format instructions,
        and guidance on inferring requirements from test evidence.
        """
        ...

    @abstractmethod
    def _find_targets(self, **filters) -> list:
        """Find all parent nodes eligible for mining.

        For an LLR miner, this returns CompoundNodes that have tests
        verifying them.

        Args:
            **filters: Arbitrary keyword filters (e.g. ``tag="as-built"``).

        Returns:
            List of neomodel node instances.
        """
        ...

    @abstractmethod
    def _fetch_context(self, target) -> dict:
        """Fetch all context needed to mine requirements for one target.

        Returns a dict with keys like ``"tests"``, ``"description"``,
        etc. — whatever the prompt builder needs.

        Args:
            target: The parent node (e.g. a ClassNode).

        Returns:
            Context dict for prompt building.
        """
        ...

    @abstractmethod
    def _build_prompt(self, target, context: dict) -> str:
        """Build the user prompt for one compound.

        Args:
            target: The parent node.
            context: The context dict from :meth:`_fetch_context`.

        Returns:
            The full user prompt string.
        """
        ...

    @abstractmethod
    def _persist_results(
        self,
        target,
        mined: MinedRequirements,
    ) -> MineResult:
        """Persist the mined HLR and LLRs to Neo4j.

        Creates HLR and LLR nodes, COMPOSES edges (HLR → LLR →
        TestNode), and optional HLR → CompoundNode edges.

        Args:
            target: The compound node.
            mined: Parsed LLM output with HLR and LLRs.

        Returns:
            A :class:`MineResult` with counts.
        """
        ...

    # ------------------------------------------------------------------
    # Optional hooks (subclasses may override)
    # ------------------------------------------------------------------

    def _should_mine_target(self, target, context: dict) -> bool:
        """Return True if this target has enough test evidence to mine.

        Default: requires at least one test in the context.
        """
        return len(context.get("tests", [])) > 0

    # ------------------------------------------------------------------
    # Template methods
    # ------------------------------------------------------------------

    def mine_one(
        self,
        target,
        *,
        model: str = "",
        dry_run: bool = False,
        overwrite: bool = False,
        max_tokens: int = 32768,
    ) -> MineResult:
        """Mine requirements for a single compound.

        Template method that orchestrates:

        1. Fetch test context from Neo4j
        2. Check eligibility
        3. Build prompt
        4. Call LLM
        5. Parse response
        6. Persist results

        Args:
            target: The compound node (e.g. a ClassNode).
            model: LLM model override.
            dry_run: If True, build the prompt but skip the LLM call.
            overwrite: If True, overwrite existing requirements.
            max_tokens: Maximum response tokens.

        Returns:
            A :class:`MineResult`.
        """
        compound_name = self.node_name(target)

        # --- 1. Fetch context ---
        context = self._fetch_context(target)

        # --- 2. Check eligibility ---
        if not self._should_mine_target(target, context):
            return MineResult(
                compound_name=compound_name,
                skipped=True,
                skip_reason="No tests found for this compound",
            )

        # --- 3. Check for existing requirements (unless overwrite) ---
        if not overwrite and self._has_existing_requirements(target):
            return MineResult(
                compound_name=compound_name,
                skipped=True,
                skip_reason="Requirements already exist (use --overwrite to replace)",
            )

        # --- 4. Dry-run: stop here ---
        if dry_run:
            test_count = len(context.get("tests", []))
            print(
                f"  {compound_name}: {test_count} tests (dry-run, not calling LLM)"
            )
            return MineResult(
                compound_name=compound_name,
                skipped=True,
                skip_reason="dry_run mode",
            )

        # --- 5. Build prompt ---
        user_prompt = self._build_prompt(target, context)

        # Scale max_tokens to test count for adequate JSON response
        test_count = len(context.get("tests", []))
        effective_max_tokens = max(max_tokens, test_count * 150 + 500)

        # --- 6. Call LLM ---
        print(
            f"  {compound_name}: {test_count} tests → calling LLM "
            f"(max_tokens={effective_max_tokens})...",
            end=" ", flush=True,
        )
        call_start = time.monotonic()

        response = ""
        mined: MinedRequirements | None = None
        batch_error: str | None = None

        try:
            response = self._call_llm(
                system=self.system_prompt,
                user=user_prompt,
                model=model,
                max_tokens=effective_max_tokens,
                call_label=compound_name,
            )
            parsed = self.parse_llm_response(response)
            mined = MinedRequirements.model_validate(parsed)
        except Exception as exc:
            batch_error = str(exc)
            log.warning(
                "Mining failed for %s: %s", compound_name, exc,
            )

        elapsed = time.monotonic() - call_start

        # --- 7. Handle failure ---
        if batch_error or mined is None:
            print(f"FAILED ({elapsed:.1f}s): {batch_error}", flush=True)
            return MineResult(
                compound_name=compound_name,
                error=batch_error or "Unknown error",
            )

        # --- 8. Persist results ---
        result = self._persist_results(target, mined)
        print(
            f"OK ({elapsed:.1f}s) — {result.llr_count} LLRs, "
            f"{result.test_count} tests linked",
            flush=True,
        )

        return result

    def mine_all(
        self,
        *,
        model: str = "",
        dry_run: bool = False,
        overwrite: bool = False,
        max_tokens: int = 32768,
        **filters,
    ) -> MineSummary:
        """Mine requirements for every eligible target in the graph.

        Args:
            model: LLM model override.
            dry_run: If True, simulate without calling the LLM.
            overwrite: If True, overwrite existing requirements.
            max_tokens: Maximum response tokens per LLM call.
            **filters: Forwarded to :meth:`_find_targets`
                (e.g. ``tag="as-built"``).

        Returns:
            A :class:`MineSummary`.
        """
        targets = self._find_targets(**filters)
        summary = MineSummary(total_compounds=len(targets))

        for i, target in enumerate(targets):
            name = self.node_name(target)
            print(f"[{i + 1}/{len(targets)}] {name}")
            try:
                result = self.mine_one(
                    target,
                    model=model,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    max_tokens=max_tokens,
                )
                summary.results.append(result)
                if result.skipped:
                    summary.total_skipped += 1
                elif result.error:
                    summary.total_errors += 1
                else:
                    summary.total_llrs += result.llr_count
                    summary.total_tests_linked += result.test_count
            except Exception as exc:
                err_result = MineResult(
                    compound_name=name,
                    error=str(exc),
                )
                summary.results.append(err_result)
                summary.total_errors += 1
                summary.errors.append(f"{name}: {exc}")

        return summary

    def _has_existing_requirements(self, target) -> bool:
        """Return True if the compound already has mined requirements.

        The base implementation returns False — override if you want
        idempotency checks.
        """
        return False
