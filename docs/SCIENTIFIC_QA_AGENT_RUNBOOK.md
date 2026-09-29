# Scientific QA agent runbook

This runbook operationalizes the seven roles in the supplied brief. Run them in the order below. Each agent reads this file, the research log, the previous handoff, relevant repository code and data manifests before it starts. Each writes a dated entry to `docs/SCIENTIFIC_QA_RESEARCH_LOG.md` with commands run, inputs and versions, evidence paths, results, limitations and a next action. A planned check is never marked passed.

| Order | Agent | First bounded assignment | Handoff condition |
| --- | --- | --- | --- |
| 1 | Research Continuity Architect | Persist research tasks, checkpoints, evidence hashes and resume instructions; test interruption handling. | A new session can inspect saved state without chat history. |
| 2 | QA Architect & Orchestrator | Inventory architecture, data and missing evidence; set up executable QA entry points and machine-readable results. | Tests and blockers are documented with exact commands. |
| 3 | Functional QA Engineer | Check one basin-selection and export path plus invalid input at a local, rate-limited target. | Reproduction steps and traces exist for failures. |
| 4 | Independent Data Auditor | Independently check a small, explicitly sourced topology or climate case. | Expected values do not originate solely from production functions. |
| 5 | Model Validation Scientist | Audit one available model claim against held-out evidence, baseline and uncertainty definition. | Unsupported claims are marked unverified. |
| 6 | Scientific Research Replicator | Select one accessible full paper and assess feasibility before computing. | DOI/URL, methods, data access and comparability are recorded. |
| 7 | Independent Scientific Reviewer | Review the earlier evidence, classify issues and set retest criteria. | Every verdict links to evidence and notes its scope. |

All agents keep production data and calculations unchanged. They do not deploy, publish, or submit scientific conclusions automatically. Missing source data or methods produce `BLOCKED` or `Not verified` with the exact missing evidence. A claim of independent validation requires a separate calculation or primary reference, not agreement among UI, API and exports that share the same implementation.

The immediate assignments above establish working agents; they do not imply that every variable, basin, paper or model has been checked. Follow-up tasks can expand coverage after the first evidence review.
