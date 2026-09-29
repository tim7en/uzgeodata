"""Run with: python -m qa.continuity --store PATH --workspace PATH COMMAND."""

import argparse
import json
import sys
from pathlib import Path

from .core import ResearchError, ResearchStore


def parser():
    p = argparse.ArgumentParser(description="Persistent scientific research registry")
    p.add_argument("--store", required=True, help="Directory for registry, outside published data")
    p.add_argument("--workspace", default=".", help="Root allowed for evidence and artifacts")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    project = sub.add_parser("project")
    project.add_argument("id")
    project.add_argument("--objective", required=True)
    project.add_argument("--question", action="append", required=True)
    project.add_argument("--scope", required=True)
    project.add_argument("--basin", action="append", required=True)
    project.add_argument("--source", action="append", required=True, help="Include dataset version in each source")
    project.add_argument("--methodology", required=True)
    task = sub.add_parser("task")
    task.add_argument("project")
    task.add_argument("id")
    task.add_argument("--title", required=True)
    task.add_argument("--owner", required=True)
    task.add_argument("--dependency", action="append", default=[])
    task.add_argument("--next", action="append", required=True)
    transition = sub.add_parser("transition")
    transition.add_argument("project")
    transition.add_argument("task")
    transition.add_argument("state")
    transition.add_argument("--actor", required=True)
    transition.add_argument("--reason", required=True)
    transition.add_argument("--validation-evidence", action="append", default=[])
    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("project")
    checkpoint.add_argument("task")
    checkpoint.add_argument("milestone")
    checkpoint.add_argument("--actor", required=True)
    checkpoint.add_argument("--input", action="append", default=[])
    checkpoint.add_argument("--output", action="append", required=True)
    checkpoint.add_argument("--parameters", default="{}", help="JSON object")
    checkpoint.add_argument("--instructions", required=True)
    checkpoint.add_argument("--code-version", required=True)
    memory = sub.add_parser("memory")
    memory.add_argument("project")
    memory.add_argument("kind")
    memory.add_argument("claim")
    memory.add_argument("--actor", required=True)
    memory.add_argument("--evidence", action="append", required=True)
    handoff = sub.add_parser("handoff")
    handoff.add_argument("project")
    handoff.add_argument("task")
    handoff.add_argument("--actor", required=True)
    for flag in ("completed", "evidence", "verified", "discrepancy", "file", "blocker", "next", "resume-command", "resource"):
        handoff.add_argument("--" + flag, action="append", required=flag in ("next", "resume-command"), default=[])
    resume = sub.add_parser("resume")
    resume.add_argument("project")
    resume.add_argument("task")
    resume.add_argument("--owner", required=True)
    resume.add_argument("--code-version", help="Compare checkpoints against current code version")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    store = ResearchStore(Path(args.store), Path(args.workspace))
    try:
        if args.command == "init":
            store.init()
            result = {"created": str(store.registry)}
        elif args.command == "status":
            result = store.status()
        elif args.command == "project":
            store.add_project(args.id, args.objective, args.question, args.scope, args.basin, args.source, args.methodology)
            result = {"created": args.id}
        elif args.command == "task":
            store.add_task(args.project, args.id, args.title, args.owner, args.dependency, args.next)
            result = {"created": args.id}
        elif args.command == "transition":
            store.transition(args.project, args.task, args.state, args.actor, args.reason, args.validation_evidence)
            result = {"status": args.state}
        elif args.command == "checkpoint":
            parameters = json.loads(args.parameters)
            if not isinstance(parameters, dict):
                raise ResearchError("Parameters must be a JSON object")
            result = store.checkpoint(args.project, args.task, args.milestone, args.input, args.output, parameters, args.instructions, args.code_version, args.actor)
        elif args.command == "memory":
            store.add_memory(args.project, args.kind, args.claim, args.evidence, args.actor)
            result = {"recorded": args.kind}
        elif args.command == "handoff":
            result = store.handoff(args.project, args.task, args.actor, args.completed, args.evidence, args.verified, args.discrepancy, args.file, args.blocker, args.next, args.resume_command, args.resource)
        else:
            result = store.resume(args.project, args.task, args.owner, args.code_version)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ResearchError, json.JSONDecodeError) as exc:
        print(f"research continuity: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
