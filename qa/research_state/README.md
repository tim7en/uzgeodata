# First-pass research backlog

`registry.json` is the persisted state for the reviewed QA follow-ups. It was created from `qa/scientific_review/triage.json` with:

```sh
python -m qa.seed_research_backlog
python -m qa.continuity --store qa/research_state --workspace . status
```

All six tasks are `PROPOSED`. This records next actions and evidence hashes; it does not approve fixes, downloads, publication, or deployment. The first-pass agent work is documented in `docs/SCIENTIFIC_QA_RESEARCH_LOG.md` and the role reports. Use the continuity CLI to inspect a task and its evidence before starting any approved follow-up. Keep this registry and the referenced evidence artifacts together when transferring work to another environment.
