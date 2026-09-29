# Research continuity

This local registry records authorized scientific work. It never runs calculations, downloads data, or modifies published datasets. Use a store directory outside `PUBLISHED/` and a workspace containing only authorized evidence files. The registry is JSON so a fresh agent can inspect it without prior conversation.

```powershell
python -m qa.continuity --store qa/research_state --workspace . init
python -m qa.continuity --store qa/research_state --workspace . project climate-001 --objective "Basin climate summary" --question "What changed?" --scope "Amu Darya basin, 2001-2020" --basin AMU --source "ERA5-Land v1, downloaded 2026-09-29" --methodology "Documented area-weighted mean; independent second implementation required"
python -m qa.continuity --store qa/research_state --workspace . task climate-001 acquire --title "Acquire source" --owner agent-a --next "Verify source checksum"
python -m qa.continuity --store qa/research_state --workspace . transition climate-001 acquire APPROVED --actor reviewer --reason "Scope approved"
python -m qa.continuity --store qa/research_state --workspace . transition climate-001 acquire IN_PROGRESS --actor agent-a --reason "Starting approved work"
python -m qa.continuity --store qa/research_state --workspace . checkpoint climate-001 acquire source-acquired --actor agent-a --output qa/artifacts/source.csv --instructions "Re-download from documented source, compare SHA-256" --code-version "git:abc123"
python -m qa.continuity --store qa/research_state --workspace . handoff climate-001 acquire --actor agent-a --completed "Source acquired" --file qa/artifacts/source.csv --next "Verify source checksum" --resume-command "python -m qa.continuity --store qa/research_state --workspace . resume climate-001 acquire --owner agent-a"
python -m qa.continuity --store qa/research_state --workspace . resume climate-001 acquire --owner agent-a
```

At session start, run `status` and `resume` for assigned tasks. Resume checks each checkpoint's input and output hashes in order and reports the last valid checkpoint. Any missing or changed file makes `safe_to_resume` false. An agent should then investigate and transition the task to `BLOCKED` with a reason, or create new approved work to reproduce the artifact. A checkpoint records only completed work; planned operations do not count.

Task progression is `PROPOSED → APPROVED → IN_PROGRESS → AWAITING_VALIDATION → VALIDATED → COMPLETED`, with `BLOCKED` and `CANCELLED` transitions. Dependency tasks must be validated before execution. The task owner cannot approve or validate their own work. Validation requires evidence files and a different actor. This records independent review but cannot prove that the underlying method is scientifically independent; reviewers must inspect the method and evidence.

The `.registry.lock` file coordinates local writers; concurrent writers fail rather than overwrite each other. Do not remove a lock until confirming its recorded process has stopped. Registry writes use a temporary file, fsync, and atomic replace. Backup the store with its artifacts for migration to another environment. A path outside the configured workspace is rejected. `limits` in the registry are conservative configuration values; the CLI enforces task concurrency, but does not execute jobs or enforce network, download, time, or storage quotas. External schedulers must enforce those limits and require authorization before any expensive service, production merge, publication, or deployment.

This component is a foundation, not a claim of passed cross-session climate research. The complete interruption and independent validation acceptance demonstration remains separate work.
