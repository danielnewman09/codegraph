"""Abstract base for LLM-based enrichment of codegraph nodes.

Provides the template-method pipeline and reusable utilities shared
across all enricher types (TestEnricher, ClassEnricher, etc.).

Concrete responsibilities of the base class:

* ``_call_llm()`` — delegates to ``llm_caller.call_text()``

Migration-only legacy service. Its current consumer is the enrichment CLI and
batch workflow; the replacement target is the shared model service. Remove
after parity and downstream migration are verified. Do not add new
orchestration behavior here.
* ``parse_llm_response()`` — extracts JSON from LLM output
* ``is_placeholder()`` — detects parser-generated placeholder descriptions
* ``node_name()`` — extracts a readable qualified name
* ``enrich_one()`` — template method: fetch → filter → prompt → call → parse → save
* ``enrich_all()`` — template method: find targets → enrich_one loop

Subclasses must implement:

* ``system_prompt`` — property returning the LLM system prompt
* ``_fetch_children(target)`` — traverse Neo4j relationships for composed children
* ``_fetch_verifies(target)`` — traverse VERIFIES edges for code-under-test context
* ``_build_prompt(target, all_children, to_enrich, verifies)`` — build the batch user prompt
* ``_find_targets(**filters)`` — query Neo4j for all eligible parent nodes
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
from typing import Any

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Result types
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class EnrichmentResult:
    """Result of enriching a single node's description.

    Attributes:
        qualified_name: The node's fully-qualified identifier.
        node_type: Category label (e.g. ``"fixture"``, ``"step"``,
            ``"method"``, ``"attribute"``).
        field: The attribute name that was enriched (default ``"description"``).
        old_description: The description before enrichment.
        new_description: The description after enrichment.
        error: Error message if enrichment failed.
        skipped: Whether this node was skipped (already had a description,
            dry-run mode, etc.).
        skip_reason: Why this node was skipped.
    """

    qualified_name: str
    node_type: str
    field: str = "description"
    old_description: str = ""
    new_description: str = ""
    error: str | None = None
    skipped: bool = False
    skip_reason: str = ""

    @property
    def changed(self) -> bool:
        """True if the description was actually modified."""
        return bool(self.new_description) and self.new_description != self.old_description

    @property
    def success(self) -> bool:
        """True if enrichment succeeded without error and changed the description."""
        return self.changed and self.error is None

    def to_dict(self) -> dict:
        return {
            "qualified_name": self.qualified_name,
            "node_type": self.node_type,
            "field": self.field,
            "old_description": self.old_description,
            "new_description": self.new_description,
            "changed": self.changed,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "error": self.error,
        }


@dataclass
class EnrichmentSummary:
    """Summary of enrichment for one target (test, class, etc.).

    ``results`` holds the flat list of per-node outcomes.  ``to_dict()``
    groups them by ``node_type`` for serialisation so callers see
    buckets like ``"fixtures"``, ``"steps"``, ``"assertions"`` (or
    ``"methods"``, ``"attributes"`` for a class enricher).

    Attributes:
        target_name: The qualified name of the enriched parent node.
        results: Flat list of individual :class:`EnrichmentResult` objects.
        errors: Non-node-specific error messages (e.g. connection failures).
        total_enriched: Count of nodes that were successfully enriched.
        total_skipped: Count of nodes that were skipped.
        total_errors: Count of nodes that failed enrichment.
    """

    target_name: str = ""
    results: list[EnrichmentResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_enriched: int = 0
    total_skipped: int = 0
    total_errors: int = 0

    def to_dict(self) -> dict:
        """Serialize with results grouped by ``node_type``.

        For a TestEnricher this produces keys like ``"fixtures"``,
        ``"steps"``, ``"assertions"``.  For a ClassEnricher it would
        produce ``"methods"``, ``"attributes"``, etc.
        """
        groups: dict[str, list[dict]] = {}
        for r in self.results:
            bucket = groups.setdefault(r.node_type + "s", [])
            bucket.append({
                "qualified_name": r.qualified_name,
                "description": r.new_description,
                "changed": r.changed,
                "error": r.error,
            })

        return {
            "target_name": self.target_name,
            "total_enriched": self.total_enriched,
            "total_skipped": self.total_skipped,
            "total_errors": self.total_errors,
            **groups,
            "errors": self.errors,
        }


# ══════════════════════════════════════════════════════════════════════════
# GraphEnricher — abstract template-method base
# ══════════════════════════════════════════════════════════════════════════


class GraphEnricher(ABC):
    """Abstract base for LLM-based enrichment of codegraph nodes.

    Subclasses define **what** to enrich (which Neo4j nodes, what
    relationships to traverse, how to build prompts) while the base
    class handles **how** (the fetch→prompt→call→parse→save pipeline,
    LLM calling, JSON parsing, placeholder detection).

    To create a new enricher, subclass and implement:

    * :meth:`system_prompt`
    * :meth:`_fetch_children`
    * :meth:`_build_prompt`
    * :meth:`_find_targets`

    Optionally override :meth:`is_placeholder` for type-specific
    placeholder patterns.

    Args:
        enrichment_field: The node attribute to read from / write to.
            Defaults to ``"description"``.  Set to a different field
            name (e.g. ``"summary"``) when enriching a different
            attribute.
    """

    def __init__(
        self,
        enrichment_field: str = "description",
        log_dir: str | None = None,
        disable_thinking: bool = True,
    ):
        self.enrichment_field = enrichment_field
        self.log_dir = Path(log_dir) if log_dir else None
        self.disable_thinking = disable_thinking

    # ------------------------------------------------------------------
    # Concrete utilities (shared across all enrichers)
    # ------------------------------------------------------------------

    @staticmethod
    def node_name(node) -> str:
        """Best-effort readable name from a neomodel node."""
        return (
            getattr(node, "qualified_name", "")
            or getattr(node, "name", "?")
        )

    @staticmethod
    def is_placeholder(desc: str) -> bool:
        """Return True if *desc* looks like a parser-generated placeholder.

        The base implementation only flags empty / whitespace-only
        strings.  Subclasses should override to add type-specific
        patterns (e.g. ``"Setup block"`` for test steps).
        """
        return not desc or not desc.strip()

    @staticmethod
    def parse_llm_response(response: str) -> dict[str, str]:
        """Parse an LLM batch response into ``qualified_name → description``.

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
                f"Failed to parse batch response JSON: {exc}"
                f"\nResponse: {text[:300]}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError(
                f"Batch response is not a JSON object: "
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

        When ``self.log_dir`` is set, full prompt + response traces are
        written to ``<log_dir>/<label>_<timestamp>.md`` (prompt) and
        ``_raw.txt`` / ``_response.md`` (LLM output).

        Args:
            system: System prompt.
            user: User message / prompt.
            model: Model override (empty = llm_caller default).
            max_tokens: Maximum tokens in the response.
            call_label: Short identifier for the log filename
                (e.g. the target qualified name).

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
                else "enrich"
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
        and per-element-type guidance (fixture vs step vs assertion,
        or method vs attribute, etc.).
        """
        ...

    @abstractmethod
    def _fetch_children(self, target) -> dict[str, list[Any]]:
        """Fetch all composed children of *target* from Neo4j.

        Args:
            target: The parent node (e.g. a ``TestNode``).

        Returns:
            Dict mapping category plural name (e.g. ``"fixtures"``,
            ``"steps"``) to list of neomodel node instances.
        """
        ...

    @abstractmethod
    def _build_prompt(
        self,
        target,
        all_children: dict[str, list[Any]],
        to_enrich: dict[str, list[Any]],
    ) -> str:
        """Build the batch user prompt for one enrichment unit.

        If the enricher needs additional context beyond composed
        children (e.g. VERIFIES targets for tests), it should fetch
        that internally — the base class is agnostic.

        Args:
            target: The parent node (for top-level context).
            all_children: *All* composed children (used for peer
                context in prompt).
            to_enrich: Subset of children that actually need new
                descriptions (these are the ones the LLM must describe).

        Returns:
            The full user prompt string.
        """
        ...

    @abstractmethod
    def _find_targets(self, **filters) -> list:
        """Find all parent nodes eligible for enrichment.

        Args:
            **filters: Arbitrary keyword filters (e.g. ``tag="as-built"``).
                The subclass interprets these for its node type.

        Returns:
            List of neomodel node instances.
        """
        ...

    # ------------------------------------------------------------------
    # Optional hooks (subclasses may override)
    # ------------------------------------------------------------------

    def _should_enrich_target(self, target) -> bool:
        """Return True if the target (parent) node itself should be enriched.

        The base implementation returns False — only composed children
        are enriched.  Override in subclasses (e.g. TestEnricher) to
        also generate a description for the parent node.
        """
        return False

    def _build_target_section(
        self, target, children: dict[str, list[Any]]
    ) -> str:
        """Return a prompt section that asks the LLM to describe the
        target node itself.  Called only when :meth:`_should_enrich_target`
        returns True and the target actually needs enrichment.

        Override in subclasses — the base returns an empty string.
        """
        return ""

    # ------------------------------------------------------------------
    # Template methods
    # ------------------------------------------------------------------

    def enrich_one(
        self,
        target,
        *,
        model: str = "",
        dry_run: bool = False,
        overwrite: bool = False,
        max_tokens: int = 32768,
    ) -> EnrichmentSummary:
        """Enrich all children of a single parent node.

        This is the main template method.  It orchestrates:

        1. Fetch children and VERIFIES targets from Neo4j
        2. Filter out nodes that already have real descriptions
        3. Build a batched LLM prompt
        4. Call the LLM
        5. Parse the JSON response
        6. Save updated descriptions back to Neo4j

        Args:
            target: The parent node (e.g. a ``TestNode``).
            model: LLM model override.
            dry_run: If True, build the prompt but skip the LLM call.
            overwrite: If True, overwrite existing descriptions.
            max_tokens: Maximum response tokens.

        Returns:
            An :class:`EnrichmentSummary`.
        """
        target_name = self.node_name(target)
        summary = EnrichmentSummary(target_name=target_name)

        # --- 1. Fetch children ---
        children = self._fetch_children(target)

        total_children = sum(len(v) for v in children.values())
        if total_children == 0:
            return summary

        # --- 2. Filter: which nodes actually need enrichment? ---
        def _needs_enrichment(node) -> bool:
            desc = getattr(node, self.enrichment_field, "")
            if desc.strip() and not overwrite and not self.is_placeholder(desc):
                return False
            return True

        to_enrich: dict[str, list[Any]] = {}
        for category, nodes in children.items():
            to_enrich[category] = [n for n in nodes if _needs_enrichment(n)]

        # Record skipped nodes
        for category, nodes in children.items():
            enrich_set = set(id(n) for n in to_enrich.get(category, []))
            for n in nodes:
                if id(n) not in enrich_set:
                    summary.results.append(EnrichmentResult(
                        qualified_name=self.node_name(n),
                        node_type=_singular(category),
                        field=self.enrichment_field,
                        old_description=getattr(n, self.enrichment_field, ""),
                        skipped=True,
                        skip_reason="Already has a description",
                    ))
                    summary.total_skipped += 1

        # --- 2b. Optionally include the target node itself ---
        if self._should_enrich_target(target):
            if _needs_enrichment(target):
                to_enrich["target"] = [target]
            else:
                summary.results.append(EnrichmentResult(
                    qualified_name=target_name,
                    node_type="target",
                    field=self.enrichment_field,
                    old_description=getattr(target, self.enrichment_field, ""),
                    skipped=True,
                    skip_reason="Already has a description",
                ))
                summary.total_skipped += 1

        total_to_enrich = sum(len(v) for v in to_enrich.values())
        if total_to_enrich == 0:
            return summary

        if not dry_run:
            parts = [
                f"{len(v)} {_singular(c)}"
                for c, v in to_enrich.items() if v
            ]
            print(f"  {target_name}: {total_to_enrich} nodes ({', '.join(parts)})")

        # --- 3. Dry-run: stop here ---
        if dry_run:
            for category, nodes in to_enrich.items():
                for n in nodes:
                    summary.results.append(EnrichmentResult(
                        qualified_name=self.node_name(n),
                        node_type=_singular(category),
                        field=self.enrichment_field,
                        old_description=getattr(n, self.enrichment_field, ""),
                        skipped=True,
                        skip_reason="dry_run mode",
                    ))
                    summary.total_skipped += 1
            return summary

        # --- 4. Build prompt and call LLM ---
        user_prompt = self._build_prompt(
            target, children, to_enrich,
        )
        # Append the target-node section if applicable
        target_section = self._build_target_section(target, children)
        if target_section:
            user_prompt += "\n" + target_section

        # Scale max_tokens to the batch size so the JSON response
        # isn't truncated.  ~100 tokens per description + overhead.
        effective_max_tokens = max(max_tokens, total_to_enrich * 100 + 200)

        print(
            f"  Calling LLM for {total_to_enrich} nodes "
            f"(max_tokens={effective_max_tokens})...",
            end=" ", flush=True,
        )
        call_start = time.monotonic()

        response = ""
        descriptions: dict[str, str] = {}
        batch_error: str | None = None

        try:
            response = self._call_llm(
                system=self.system_prompt,
                user=user_prompt,
                model=model,
                max_tokens=effective_max_tokens,
                call_label=target_name,
            )
            descriptions = self.parse_llm_response(response)
        except Exception as exc:
            batch_error = str(exc)
            log.warning(
                "Enrichment failed for %s: %s", target_name, exc,
            )

        elapsed = time.monotonic() - call_start

        # --- 5. Handle batch failure ---
        if batch_error:
            print(f"FAILED ({elapsed:.1f}s): {batch_error}", flush=True)
            for category, nodes in to_enrich.items():
                for n in nodes:
                    qn = self.node_name(n)
                    summary.results.append(EnrichmentResult(
                        qualified_name=qn,
                        node_type=_singular(category),
                        field=self.enrichment_field,
                        old_description=getattr(n, self.enrichment_field, ""),
                        error=batch_error,
                    ))
                    summary.total_errors += 1
                    summary.errors.append(f"{qn}: {batch_error}")
            return summary

        # --- 6. Apply results back to Neo4j ---
        enriched_count = 0
        for category, nodes in to_enrich.items():
            nt = _singular(category)
            for n in nodes:
                qn = self.node_name(n)
                old_desc = getattr(n, self.enrichment_field, "")
                new_desc = descriptions.get(qn, "")

                er = EnrichmentResult(
                    qualified_name=qn,
                    node_type=nt,
                    field=self.enrichment_field,
                    old_description=old_desc,
                    new_description=new_desc,
                )

                if new_desc and new_desc != old_desc:
                    setattr(n, self.enrichment_field, new_desc)
                    try:
                        n.save()
                    except Exception as exc:
                        er.error = f"save failed: {exc}"
                        summary.total_errors += 1
                        summary.errors.append(
                            f"{qn}: save failed: {exc}"
                        )
                    else:
                        summary.total_enriched += 1
                        enriched_count += 1
                else:
                    er.skipped = True
                    er.skip_reason = (
                        "LLM returned empty or missing key"
                    )
                    summary.total_skipped += 1

                summary.results.append(er)

        unchanged = total_to_enrich - enriched_count
        parts = [f"{enriched_count} enriched"]
        if unchanged:
            parts.append(f"{unchanged} unchanged")
        print(f"OK ({elapsed:.1f}s) — {', '.join(parts)}", flush=True)

        return summary

    def enrich_all(
        self,
        *,
        model: str = "",
        dry_run: bool = False,
        overwrite: bool = False,
        max_tokens: int = 32768,
        **filters,
    ) -> dict[str, EnrichmentSummary]:
        """Enrich every matching target node in the graph.

        Args:
            model: LLM model override.
            dry_run: If True, simulate without calling the LLM.
            overwrite: If True, overwrite existing descriptions.
            max_tokens: Maximum response tokens per LLM call.
            **filters: Forwarded to :meth:`_find_targets`
                (e.g. ``tag="as-built"``).

        Returns:
            Dict mapping ``target_name`` → :class:`EnrichmentSummary`.
        """
        targets = self._find_targets(**filters)
        results: dict[str, EnrichmentSummary] = {}
        total = len(targets)

        for i, target in enumerate(targets):
            name = self.node_name(target)
            print(f"[{i + 1}/{total}] {name}")
            try:
                results[name] = self.enrich_one(
                    target,
                    model=model,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                results[name] = EnrichmentSummary(
                    target_name=name,
                    errors=[str(exc)],
                )

        return results


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════


def _singular(plural: str) -> str:
    """Naive plural→singular for category names.

    >>> _singular("fixtures")
    'fixture'
    >>> _singular("steps")
    'step'
    >>> _singular("target")
    'target'
    """
    if plural == "target":
        return "target"
    if plural.endswith("ies"):
        return plural[:-3] + "y"
    if plural.endswith("ses"):
        return plural[:-2]
    if plural.endswith("s"):
        return plural[:-1]
    return plural
