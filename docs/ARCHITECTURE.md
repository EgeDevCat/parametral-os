# Ultra SI OS — Architecture (v1)

Stack decision: **Arch tabanı + Nix** (pacman for system packages, `nix`/home-manager for the
rootless user profile). The layer itself is distro-agnostic — package commands live in policy,
not in code — but the shipped policy, the sandbox bind layout and the test host are Arch/Nix.

```
┌─────────────────────────────────────────────────────────────────┐
│ Ultra SI local AI (Berkay) — GC Shield lives HERE, in the weights│
│   soft layer: adversarial-trained + DPO refusals, probabilistic  │
└───────────────┬─────────────────────────────────────────────────┘
                │ JSON-RPC 2.0 / NDJSON over AF_UNIX   (docs/API-v1.md)
┌───────────────▼─────────────────────────────────────────────────┐
│ ultraosd (gateway)                                              │
│   0. hard-deny oracle ──► separate process, signed read-only list│
│   1. policy engine (default deny, approval flags)                │
│   2. capability tokens (HMAC, TTL, use cap, node scope)          │
│   3. approval gate (human, HMAC approver proof)                  │
│   4. sandbox manager (bwrap + seccomp guard + cgroup v2)         │
│   5. audit chain (append-only, hash-linked, tamper-evident)      │
└───────────────┬─────────────────────────────────────────────────┘
                │ namespaces / seccomp / cgroups / btrfs
┌───────────────▼─────────────────────────────────────────────────┐
│ Arch + Nix host (read-only binds only; no host writes from AI)   │
└─────────────────────────────────────────────────────────────────┘
```

## Three layers, three failure modes

1. **GC Shield — in-model, soft.** 1.800 adversarial examples + DPO refusal training. It makes
   the model less likely to *produce* harmful intent. It is probabilistic, it has no socket, and
   it can be jailbroken. Therefore it is **not** a gate: nothing in this repo queries it.
2. **Hard-deny oracle — separate process, hard.** `harddenyd` holds `policy/hard_deny.v1.json`:
   tier-2 rules (disk-destroying tools, `modprobe`/`kexec`, `/boot/**`, `/etc/shadow`, credential
   paths, `/dev/**` mounts, the policy and key files themselves). Deterministic: same request,
   same verdict, no model in the loop. The list is read-only and **Ed25519-signed**: the oracle
   verifies with the *public* key only (`policy/hard_deny.v1.pub`), so owning the daemon's uid
   does not let you sign a weakened list — the private key stays with root / offline. It refuses
   to load a tampered or unsigned list, and it **watches the list and signature at runtime**
   (inotify + hash polling): any change shuts the oracle down, and the gateway then fails closed.
   The socket also accepts only allow-listed uids (`SO_PEERCRED`), so an arbitrary process cannot
   probe the list. A denial here is final — no approval is offered, because a human cannot
   authorise a disk format through an AI. Oracle unreachable → **fail closed** (`-32013`):
   "cannot check" must never mean "allowed".
3. **Sandbox — physical.** bubblewrap namespaces (user, pid, net, ipc, uts, cgroup, mount),
   `--cap-drop ALL`, `no_new_privs`, in-sandbox seccomp blacklist, cgroup v2 quotas. Blast
   radius: one directory + one cgroup. A kernel LPE is out of scope until the microVM phase.

## Autonomy tiers (what needs a human, and what must not)

| tier | scope | gate | why |
|---|---|---|---|
| **0** | sandbox work; `host.nix_profile` (rootless, generation-based) | token auto-issued, **no human** | autonomy must not die of approvals; `nix-env --rollback` is the undo |
| **1** | real system writes: `$HOME` files, `pacman -S`, services, opening network | **approval + pre-change snapshot** | real blast radius, real undo handle |
| **2** | `hard_deny.v1.json` | deterministic refusal, **no approval path** | irreversible or trust-destroying |

Approval fatigue is a security bug: if every `home-manager switch` asks a human, the human starts
clicking yes. Tier 0 keeps the question rate near zero so Tier 1 questions stay meaningful.

## Trust boundaries

1. **AI → gateway**: untrusted. Every field validated, every call oracle-checked, policy-checked
   and audited. The AI has no root, no host fd, no policy-write, no oracle-write.
2. **gateway → sandbox**: the sandbox is untrusted *after* creation. The AI can install anything
   inside it; damage stays inside the sandbox root and its cgroup.
3. **gateway → host**: the only privileged acts are mount/namespace setup (done by bwrap on
   behalf of the *user*, not root), cgroup creation inside the user's delegated subtree, and
   (phase 4) btrfs snapshots via a root-owned helper with a fixed command set. The daemon is
   never given root.

What v1 deliberately does **not** do: no microVM, no swarm, no sandbox-escape hardening beyond
the kernel's own (a kernel LPE from inside the sandbox is out of scope until the Firecracker
phase — the seccomp blacklist, `--cap-drop ALL` and user-namespace-only privileges raise the
cost, they do not prove safety).

## Phase plan (each phase ships code + tests)

| phase | scope | status |
|---|---|---|
| 1 | API v1 contract, policy engine, tokens, approvals, audit chain, bwrap sandbox, exec/fs, tier-2 oracle, CLI | **done (this delivery)** |
| 2 | `host.nix_profile` (tier 0) + `host.apply` (tier 1, snapshot-first; closed preset list already enforced), `app.*` install pipeline (manifest → deps → install → verify → ≤3 attempts → honest report) | next |
| 3 | per-sandbox disk quota (btrfs qgroup), streaming output limits, quota dashboards | next |
| 4 | btrfs snapshot/restore (sandbox root + home, unprivileged), pre-restore safety snapshot | **done for sandboxes**; host-level snapshots need the root helper |
| 5 | microVM profile (Firecracker/KVM behind `profile:"microvm"`), off-host audit anchor, root-owned operator key, swarm behind reserved methods | reserved |

## Non-negotiable invariants (tested)

- Tier 2 always wins: a *valid* token plus a permissive policy still cannot run a hard-denied
  operation (`tests/test_harddeny.py::test_valid_token_cannot_override_hard_deny`).
- Tier 1 has no generic exec path: only reviewed presets, and an interpreter/absolute
  path/metacharacter/unknown flag is refused (`tests/test_hostapply.py`).
- A rule file that changes while the oracle runs stops the oracle (`RuntimeFileWatchTest`), and a
  foreign uid on the oracle socket is refused (`PeerCredentialTest`).
- Oracle down = everything state-changing refused, diagnostics still answer (`OracleDownTest`).
- No token, no state change; token scope (sandbox, paths, commands, uses, node) is enforced.
- Default deny: an operation without a matching allow rule never executes.
- Sandbox: no network, no host home, no host write access, `CapEff=0`, uid≠0, mount/ptrace EPERM.
- Every accepted/denied/critical request appends one audit record; the chain detects edits,
  deletions and truncation.
- Errors are never swallowed: no bare `except:`, failures surface as `state:"failed"` with real
  stderr and are logged (`grep -rn "except:" src/` must be empty).

## Known limitations (honest list, milestone noted)

1. Audit immutability is *tamper-evident*, not tamper-proof: the daemon's uid (and root) can
   rewrite the chain. Off-host anchoring is phase 5.
2. **Signature keys are asymmetric now (Ed25519), but still not root-owned in development.** The
   oracle only needs the public key, so reading it earns an attacker nothing; however the dev
   signing key sits in `~/.local/state/ultraos/keys/hard_deny.ed25519.sk`. Production must keep it
   root-owned (or in a TPM/HSM/offline machine) and run `sign` outside the AI's uid — otherwise a
   same-uid AI could sign its own list. Same for the approver HMAC key (needs a separate approver
   uid). Until then the oracle protects against a *jailbroken model*, not a compromised account.
3. Per-sandbox *total* disk quota needs btrfs qgroups (root): v1 enforces per-file `RLIMIT_FSIZE`
   and reports the effective limit.
4. `RLIMIT_NPROC` is not used (it is per-uid and would break the sandbox for heavy users);
   process limits come from `pids.max` in cgroup v2.
5. Sandbox is a container, not a VM: shared kernel. microVM profile is phase 5.
6. No GPU, no display, no dbus passthrough in v1 — GUI apps are out of scope until phase 5.
7. `harddenyd` and `ultraosd` may share a uid in development; production runs them as separate
   units with root-owned, read-only rule files.
8. `sysapply` runs as root on the target image and is tested here with a stubbed `pacman` and a
   scratch spool: the signature hand-off, preset validation, snapshot ordering and refusal paths
   are covered, an actual root install is not (that needs the installed system).
8. Unprivileged `btrfs subvolume delete` needs `CAP_SYS_ADMIN` (or `user_subvol_rm_allowed`).
   Creating and restoring snapshots works anyway; replaced subvolumes are parked in
   `<state>/trash` and must be reclaimed by root. `snapshot.restore` reports
   `space_reclaim_needs_root` instead of hiding it.
9. Snapshots cover a sandbox (root + home), not the host filesystem: host-level rollback needs
   the root-owned helper planned for phase 2/4.
