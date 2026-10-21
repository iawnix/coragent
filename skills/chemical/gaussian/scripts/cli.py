"""Pure argument contract shared by request preparation and execution."""
import argparse
import re
import sys

def parse_arguments(argv=None):
    p = argparse.ArgumentParser(
        description="Gaussian explicit input or XYZ opt/SP", allow_abbrev=False,
        epilog="chemical.gaussian: --input geometry=file.xyz, then -- --task opt/sp/opt-sp; "
               "omit --validation. chemical.gaussian-input: --input input=file.gjf, then "
               "-- --validation opt/sp/frequency/minimum/saddle/irc/none; omit --task. "
               "Neither mode supports --task-validation. The preparer supplies --xyz/--input-gjf, "
               "--executable and --output-dir. Submit its request_file and request_sha256 with job_start.")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--xyz', help='XYZ shortcut; requires --task, which also selects runner checks')
    source.add_argument('--input-gjf', help='Run an explicit Gaussian input, including TS/Freq/IRC/QST/scan routes')
    p.add_argument('--task', choices=['opt','sp','opt-sp'], help='XYZ only: calculation and its checks; omit --validation')
    p.add_argument('--validation', choices=['none','opt','sp','frequency','minimum','saddle','irc'], default='none',
                   help='Explicit GJF only: checks for the supplied route, not a request to change it (default: none)')
    p.add_argument('--executable', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--method', default='M062X')
    p.add_argument('--basis', default='6-31G**')
    p.add_argument('--charge', type=int, default=0)
    p.add_argument('--multiplicity', type=int, default=1, help='spin multiplicity 2S+1')
    p.add_argument('--threads', type=int, default=1)
    p.add_argument('--memory-mb', type=int, default=2000)
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg.split('=', 1)[0] == '--task-validation' for arg in argv):
        p.error('--task-validation is not supported. For XYZ, remove it and keep --task opt/sp/opt-sp. '
                'For explicit GJF, use --validation opt/sp/frequency/minimum/saddle/irc/none.')
    a=p.parse_args(argv)
    if a.input_gjf and a.task:
        p.error('--task is only for the XYZ shortcut; remove --task for explicit GJF and use --validation '
                'to select checks. The GJF route defines the calculation.')
    if a.xyz and not a.task: p.error('--xyz requires --task opt/sp/opt-sp')
    if a.xyz and a.validation != 'none':
        p.error(f'--validation requires --input-gjf; remove --validation {a.validation} and keep --task {a.task} '
                'for XYZ. For frequency/minimum/saddle/irc checks, prepare an explicit GJF with the required route '
                'and use chemical.gaussian-input.')
    if a.multiplicity < 1 or a.threads < 1 or a.memory_mb < 1: p.error("invalid multiplicity/resources")
    if not all(re.fullmatch(r"[A-Za-z0-9+*(),._-]+", v) for v in [a.method,a.basis]):
        p.error("method/basis must be single Gaussian route tokens")
    return a
