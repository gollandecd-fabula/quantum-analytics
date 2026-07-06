# Run As User Report — One-Click Stable Release

Date: 2026-07-06
Branch: `fix/quantum-one-click-stable-release`

## Status

`BLOCKED`

## Required user scenario

The required scenario was: download one file, run it, install/update local runtime, preserve `config`, `data`, `output`, create a desktop shortcut, start Quantum, open the browser, and show `READY`, `DEGRADED`, or `BLOCKED`.

## Actual execution

The user-like run was not executed.

## Command attempted before run

```text
git clone https://github.com/gollandecd-fabula/quantum-analytics.git /mnt/data/quantum-analytics
```

Result:

```text
fatal: unable to access 'https://github.com/gollandecd-fabula/quantum-analytics.git/': Could not resolve host: github.com
```

Exit code: `128`

## Reason the user-like run is blocked

The runtime environment could not obtain a local checkout. Without a local checkout and without a verified one-click package, it is not possible to execute the installer, create a shortcut, start the app, or open `localhost` as a user.

## Current known manual runtime command from existing documentation

```text
PYTHONPATH=src python -m quantum.api.main --host 127.0.0.1 --port 8080
```

This is a manual developer command, not a verified one-click user launch.

## Conclusion

Do not claim that one-click launch works. Current result is `BLOCKED`.