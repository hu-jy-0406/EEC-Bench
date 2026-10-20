# Sandbox network-namespace failure

Host: auh-1b-cpu-login-001

Minimal diagnostics (no persistent configuration changes):

- `unshare --user --map-root-user true`: succeeds.
- `unshare --user --map-root-user --mount true`: succeeds.
- `unshare --user --map-root-user --pid --fork true`: succeeds.
- `unshare --user --map-root-user --net true`: fails, Cannot allocate memory.
- strace: `unshare(CLONE_NEWUSER|CLONE_NEWNET) = -1 ENOMEM`.
- Inspected all 26 current account processes; readable net namespaces are the host network namespace, no network-namespace file-descriptor holders found within bounded inspection (first 256 FDs per process). `/run/netns` is empty.

Previous cleanup removed 100 stale empty pyright temporary directories; sandbox failure persisted. Disk space is available. Swap exhaustion alone does not establish the cause.

No user-owned leaked network namespace suitable for cleanup was identified. No process was killed and no sysctl, service, shared memory, network configuration, or sandbox policy was changed. Root cause remains unresolved; node administrator should investigate network namespace initialization failures/kernel diagnostics. Reconnecting Codex is not an established fix.

Image endpoints remain pending; sources and prompts are preserved in this directory.
