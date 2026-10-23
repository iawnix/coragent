"""Qrun fixture runtime inside the test runner's private process namespace.

Exercises the real queue, daemon and wrapper without requiring user systemd in
ordinary tests. Real cgroup enforcement is covered by the system-services lane.
"""
import subprocess
import sys

from research_agent.jobs import qrun


class Runtime:
    def __init__(self, root):
        self.root = root
        self.processes = {}

    def probe(self):
        pass

    def start(self, job):
        self.processes[job['id']] = subprocess.Popen(
            [sys.executable, '-B', qrun.__file__, '--state-dir', str(self.root), '_run', job['id']],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def inspect(self, job):
        process = self.processes.get(job['id'])
        if process is None:
            return {'state': 'missing'}
        code = process.poll()
        return {'state': 'running'} if code is None else {
            'state': 'finished', 'result': 'success' if code == 0 else 'exit-code', 'exit_code': code}

    def stop(self, job):
        process = self.processes.get(job['id'])
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    def cleanup(self, job):
        self.stop(job)
        self.processes.pop(job['id'], None)
        return True


def serve(root, work):
    """Stop fixture children on teardown; production daemons preserve jobs."""
    original = qrun.Queue

    class FixtureQueue(original):
        def close(self):
            try:
                for job in self.rows():
                    self.runtime.cleanup(job)
            finally:
                super().close()

    qrun.initialize(root, 64, 131072, [str(work)])
    qrun.Systemd = Runtime
    qrun.Queue = FixtureQueue
    qrun.serve(root)


if __name__ == '__main__':
    from pathlib import Path
    serve(Path(sys.argv[1]), Path(sys.argv[2]))
