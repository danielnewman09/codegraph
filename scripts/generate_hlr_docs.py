#!/usr/bin/env python3
"""Generate one markdown document per HLR with full requirement→test→design stack."""
import os
from neo4j import GraphDatabase

d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'codegraph'))

with d.session() as s:
    r = s.run('''
        MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR)
        WHERE "design" IN hlr.tags
        OPTIONAL MATCH (test:TestNode)-[:VERIFIES]->(llr)
        OPTIONAL MATCH (test)-[:COMPOSES]->(step:TestStepNode)
        OPTIONAL MATCH (step)-[:CALLEE]->(target)
        RETURN hlr.name as hlr_name, hlr.description as hlr_desc,
               llr.name as llr_name, llr.description as llr_desc,
               test.name as test_name, test.description as test_desc,
               step.name as step_name, step.description as step_desc,
               target.name as target_name, target.qualified_name as target_qname,
               labels(target) as target_labels
        ORDER BY hlr_name, llr_name, test_name, step_name
    ''')

    hlr_data = {}
    for rec in r:
        h = rec['hlr_name']
        if h not in hlr_data:
            hlr_data[h] = {'desc': rec['hlr_desc'], 'llrs': {}}
l_name = rec['llr_name']
        if l_name and l_name not in hlr_data[h]['llrs']:
            hlr_data[h]['llrs'][l_name] = {'desc': rec['llr_desc'], 'tests': {}}
        t_name = rec['test_name']
        if t_name and l_name and t_name not in hlr_data[h]['llrs'][l_name]['tests']:
            hlr_data[h]['llrs'][l_name]['tests'][t_name] = {
                'desc': rec['test_desc'], 'steps': [], 'targets': set()
            }
        step_name = rec['step_name']
        step_desc = rec['step_desc'] or ''
        target_qname = rec['target_qname']
        if t_name and step_name:
            hlr_data[h]['llrs'][l_name]['tests'][t_name]['steps'].append(
                (step_name, step_desc)
            )
            if target_qname:
                hlr_data[h]['llrs'][l_name]['tests'][t_name]['targets'].add(
                    target_qname
                )

out_dir = 'codegraph/requirements/generated/hlr_docs'
os.makedirs(out_dir, exist_ok=True)

hlr_slugs = {
    'Architecture Diagram Generator \u2014 Unified Module View': '01_unified_module_view',
    'Architecture Diagram Generator \u2014 Query Integration': '02_query_integration',
    'Architecture Diagram Generator \u2014 HLR/LLR Traceability': '03_traceability',
    'Architecture Diagram Generator \u2014 Markdown Serialization': '04_markdown_serialization',
}

for hlr_name, slug in hlr_slugs.items():
    data = hlr_data.get(hlr_name, {'desc': '', 'llrs': {}})

    lines = []
    lines.append(f"# {hlr_name}")
    lines.append("")
    lines.append("> **Source**: Neo4j codegraph, `design` tag — deterministic, no LLM enrichment")
    lines.append("> **Generated**: `scripts/generate_hlr_docs.py`")
    lines.append("> **Regenerate**: `python scripts/generate_hlr_docs.py`")
    lines.append("")
    lines.append("## Description")
    lines.append("")
    desc = data['desc'].replace('\n', ' ').strip()
    lines.append(desc)
    lines.append("")
    lines.append("---")
    lines.append("")

    all_llrs = sorted(data['llrs'].items())
    covered = sum(1 for _, ld in all_llrs if ld['tests'])
    lines.append(f"**{covered}/{len(all_llrs)} LLRs verified**")
    lines.append("")

    all_targets = set()

    for llr_name, llr_data in all_llrs:
        lines.append(f"## {llr_name}")
        lines.append("")
        llr_desc = llr_data['desc'].replace('\n', ' ').strip()
        lines.append(f"{llr_desc}")
        lines.append("")

        tests = sorted(llr_data['tests'].items())
        if not tests:
            lines.append("> ⚠ No tests defined for this LLR.")
            lines.append("")
            continue

        for test_name, test_data in tests:
            lines.append(f"### `{test_name}`")
            lines.append("")
            test_desc = test_data['desc'].replace('\n', ' ').strip()
            lines.append(f"{test_desc}")
            lines.append("")

            if test_data['steps']:
                lines.append("**Steps:**")
                lines.append("")
                for i, (sname, sdesc) in enumerate(test_data['steps'], 1):
                    short = sname.split('.')[-1]
                    lines.append(f"{i}. **{short}** — {sdesc}")
                lines.append("")

            if test_data['targets']:
                all_targets.update(test_data['targets'])
                lines.append("**Exercises:**")
                lines.append("")
                for tq in sorted(test_data['targets']):
                    lines.append(f"- `{tq}`")
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Design Elements Exercised")
    lines.append("")
    for tq in sorted(all_targets):
        if '::' in tq:
            lines.append(f"- `{tq}` — method")
        else:
            lines.append(f"- `{tq}` — function")
    lines.append("")

    path = os.path.join(out_dir, f'{slug}.md')
    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    llr_count = len(all_llrs)
    test_count = sum(len(ld['tests']) for _, ld in all_llrs)
    print(f'Wrote {path} ({llr_count} LLRs, {test_count} tests)')

d.close()
print('\nDone!')
