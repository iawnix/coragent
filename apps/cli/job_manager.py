#!/usr/bin/env python3
"""Generic Job monitor CLI used by the Host wake worker."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
from _bootstrap import bootstrap_python_package
bootstrap_python_package(ROOT, workspace_from_argv=True)
from research_agent.application.job_manager import command
from research_agent.jobs.command_scope import cancel_observation_on_signal


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['observations','tick','pending','claim','event','complete','health','list','status'])
    p.add_argument('--root',required=True)
    for name in ['monitor-id','event-id','request-id','channel','claim-token','error']:p.add_argument('--'+name)
    p.add_argument('--timeout-seconds',type=float,default=30)
    p.add_argument('--delivered',action='store_true')
    a=p.parse_args()
    try:
        with cancel_observation_on_signal():
            print(json.dumps(command(a.root,a.command,vars(a))))
        return 0
    except Exception as exc:print(json.dumps({'error':str(exc)}),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
