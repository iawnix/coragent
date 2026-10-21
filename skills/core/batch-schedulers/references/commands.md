# Native commands and diagnosis

| Scheduler | Submit | Observe | Cancel |
| --- | --- | --- | --- |
| OpenPBS / PBS Pro | `qsub -q batch -l select=1:ncpus=4:mem=4096mb -l walltime=01:00:00 run.sh` | `qstat -x -f -F json JOB_ID` | `qdel JOB_ID` |
| Torque | `qsub -q batch -l nodes=1:ppn=4 -l mem=4096mb -l walltime=01:00:00 run.sh` | `qstat -x JOB_ID` | `qdel JOB_ID` |
| Slurm | `sbatch --partition=batch --cpus-per-task=4 --mem=4096 --time=60 run.sh` | `squeue -j JOB_ID`; `sacct -X -j JOB_ID -o JobID,State,ExitCode` | `scancel JOB_ID` |

The handler passes the shared working directory, separate scheduler logs and a
stable recovery identity. PBS GPU requests add `ngpus` to `select`; Slurm uses
`--gpus`. Torque GPU syntax is site-specific: adapt that resource translation to
the cluster before using it. An explicit PBS `select` replaces individual CPU,
memory and GPU fields.

PBS `Q/W` means queued, `H/S` held, `R/E` running (including cleanup). `F/C` plus
an exit code establishes completion. Slurm `PENDING`, `RUNNING`, `COMPLETING` and
terminal accounting states are treated separately. Slurm exit signals are
included in the normalized exit code. A missing job record remains unknown.

For queue waits, inspect PBS `comment`/resource fields or Slurm `%R`, then compare
requested walltime, memory, CPU count and node features with partition limits.
Sites using Maui/Moab can run `checkjob JOB_ID` for feasibility explanations.
For failures, inspect `logs/scheduler.stdout`, `logs/scheduler.stderr`, then
`logs/stdout.log` and `logs/stderr.log`. A native cancellation reply acknowledges
the request; final accounting confirms termination. CoRAgent's wrapper separately
records a walltime timeout so a program's own exit 124 remains a program failure.
