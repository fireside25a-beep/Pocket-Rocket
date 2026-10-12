# User-space service wrapper

`scripts/run_user_daemon.sh` is a real restart loop for the existing local
`neuro-inverse serve` command. It binds through the service's loopback-only
implementation, rejects ports at or below 1024, records the exact launch line,
and writes one immutable log per launch under `var/log/`. It does not invoke
`sudo`, modify cron, install systemd units, tune the kernel, or delete old logs.

Run it directly after the environment is built:

```bash
POCKET_ROCKET_ROOT="$PWD" ./scripts/run_user_daemon.sh
```

An optional user-owned cron entry is shown below for the operator to review and
install manually. The project never edits the user's crontab:

```cron
@reboot POCKET_ROCKET_ROOT=/absolute/path/to/Pocket_Rocket_DeepSeek_V4_Flash_256_MoE /absolute/path/to/Pocket_Rocket_DeepSeek_V4_Flash_256_MoE/scripts/run_user_daemon.sh
```

The wrapper does not apply `RLIMIT_AS`: an 86.72 GiB file mapping may exceed an
address-space limit while keeping only bounded pages resident. The guarded ds4
transport enforces the 14.5 GiB process-tree RSS ceiling. A future native
windowed loader may arm `RLIMIT_AS` only after proving that its total virtual
mapping stays below the cap, as recorded in `CPU_ONLY_V1_SPEC_REVIEW.md`.
