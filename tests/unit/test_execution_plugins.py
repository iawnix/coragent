from pathlib import Path

from research_agent.jobs import RemoteSSHPlatform, platforms_from_config


def test_remote_scheduler_drivers_share_ssh_platform(tmp_path: Path) -> None:
    config = tmp_path / "job.toml"
    config.write_text(
        """[execution]
default_target = "local"

[execution.targets.local]
type = "local"
driver = "process"

[execution.targets.slurm]
type = "remote"
driver = "slurm"
cluster_name = "1w"
ssh_host = "login.1w"
remote_root = "/scratch/coragent"

[execution.targets.tri]
type = "remote"
driver = "tri"
cluster_name = "tri"
ssh_host = "tri-login"
remote_root = "/scratch/coragent"
""",
        encoding="utf-8",
    )
    platforms, default = platforms_from_config(config)
    assert default == "local"
    assert isinstance(platforms["slurm"], RemoteSSHPlatform)
    assert platforms["slurm"].scheduler == "slurm"
    assert platforms["tri"].scheduler == "tri"
    assert platforms["tri"].cluster_name == "tri"


def test_slurm_submission_uses_scheduler_native_resource_flags(tmp_path: Path) -> None:
    from research_agent.jobs import JobSpec

    platform = RemoteSSHPlatform({"ssh_host": "login", "remote_root": "/scratch", "scheduler": "slurm"})
    spec = JobSpec(command=("/bin/true",), cwd=tmp_path, job_id="job_1",
                   metadata={"queue": "short", "resources": {"cpus": 2, "memory_mb": 512}})
    args = platform._submit_arguments(spec)
    assert "--partition=short" in args
    assert "--cpus-per-task=2" in args
    assert "--mem=512" in args
