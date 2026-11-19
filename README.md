<div align="center">

<h1>Parametral OS</h1>

<p><b>An Arch + Nix system an AI can operate — but never own.</b></p>

<!-- Logo buraya: dosyayı assets/parametral-mark.png olarak ekleyip alt satırın yorumunu kaldır
<img src="assets/parametral-mark.png" width="180" alt="ParametrionOS">
-->

<p>
  <img alt="tests" src="https://img.shields.io/badge/tests-133%20passing-brightgreen">
  <img alt="api" src="https://img.shields.io/badge/api-v1.2-blue">
  <img alt="sandbox" src="https://img.shields.io/badge/sandbox-bwrap%20%2B%20seccomp%20%2B%20cgroup%20v2-informational">
  <img alt="platform" src="https://img.shields.io/badge/platform-Arch%20%2B%20Nix-1793d1">
</p>

<p><sub>Arch · Nix · bubblewrap · cgroup v2 · btrfs · Ed25519 · Python 3.12+ (stdlib only)</sub></p>

</div>

The AI is treated as untrusted code with good intentions. It gets one JSON-RPC socket, a
short-lived capability token per operation, a sandbox per job, and a human gate for anything
that touches the real machine. A separate deterministic oracle refuses a fixed set of
irreversible operations before policy, tokens or approvals are even consulted. Every accepted,
refused and critical request lands in a hash-chained audit log.

Nothing here is a chatbot feature. This is the part that decides whether an autonomous agent is
allowed to run `rm -rf` on your machine — and it answers "no" from a place the model cannot reach.

## Target vs today

| | target | today |
|---|---|---|
| AI installs an app | Tier 0: sandboxed, no human | sandbox + `exec`/`fs` API work; Nix-first `app.install` is phase 2 (`-32008`) |
| AI changes the real system | Tier 1: approval + snapshot, closed preset list | presets validated and tested; executor is phase 2 |
| catastrophic command | Tier 2: deterministic refusal | implemented, Ed25519-signed, fail-closed |
| rollback | one command | sandbox snapshots/restore work (btrfs, unprivileged); host-level needs the root helper |
| distribution image | bootable Arch + Nix ISO | not built yet (roadmap A1–A4) |

## Phase status

| phase | contents | state |
|---|---|---|
| 1 | API v1.2, policy engine, tokens, approvals, audit chain, bwrap sandbox, exec/fs, tier-2 oracle, CLI | **done** — 133 tests, isolation proof |
| 2 | Nix-first `app.install`, `host.nix_profile` + `host.apply` executors (snapshot-first) | next |
| 3 | btrfs qgroup disk quota per sandbox, streaming output limits | planned |
| 4 | host-level snapshots via root helper, off-host audit anchor | planned |
| 5 | microVM profile (`profile:"microvm"`), multi-node (methods reserved, no swarm code) | reserved |

## How a request is decided

```
hard-deny oracle  →  policy (default deny)  →  capability token  →  handler  →  audit
 deterministic          allow / approval        Ed25519 + TTL       sandbox    hash chain
 signed, read-only      no rule → deny          scope + use cap     cgroup     tamper-evident
```

- **GC Shield** is in-model training (adversarial examples + DPO refusals). Soft, probabilistic,
  no socket — nothing in this repo queries it.
- **Oracle** (`harddenyd`) is a separate process: signed read-only rules, public-key verification,
  `SO_PEERCRED`-gated socket, self-closing if its rules change at runtime, fail-closed if absent.
- **Tiers**: 0 = sandbox / rootless Nix profile (no human), 1 = real system write (approval +
  snapshot, reviewed presets only), 2 = hard-deny list (no approval path exists).

## Layout

| path | what |
|---|---|
| `docs/API-v1.md` | the wire contract, frozen v1.2.0 — the AI codes against this |
| `docs/ARCHITECTURE.md` | three layers, three tiers, trust boundaries, honest limitations |
| `docs/ROADMAP.md` | three-actor plan v0.3: Arch base / AI / this layer / OS mind |
| `src/ultraos/` | gateway, policy, tokens, approvals, audit, sandbox, oracle, tier-1 validator |
| `src/ultraos_guard.c` | in-sandbox seccomp + rlimit guard (compiled to `bin/seccomp_guard`) |
| `policy/policy.v1.json` | allow/approval rules, default deny |
| `policy/hard_deny.v1.json` + `.sig` + `.v1.pub` | tier-2 list, Ed25519-signed |
| `tests/` | 133 unittest cases, no third-party deps |
| `proofs/isolation-proof.txt` | generated isolation evidence (20+ checks) |

## Build and run (fish)

```fish
cd ~/Desktop/Development/ultra-si-os
make guard                 # static seccomp guard
make test                  # 133 tests, expect "OK"
make proof                 # writes proofs/isolation-proof.txt, expect "RESULT: PASS"
bash scripts/smoke.sh      # two real processes, real sockets, expect "SMOKE OK"
```

Run it for real (two units in production, two terminals here):

```fish
bin/harddeny keygen        # once: Ed25519 keypair; private key stays with the operator
bin/harddeny sign          # sign policy/hard_deny.v1.json
bin/harddeny verify        # verify with the public key only
bin/harddenyd              # terminal 1: tier-2 oracle
bin/ultraosd               # terminal 2: gateway

bin/ultraos status
bin/ultraos sandbox create demo --auto-permission
bin/ultraos exec <sandbox_id> --auto-permission -- wipefs -a /dev/sda   # refused, tier 2
bin/ultraos audit verify
```

## The API in four lines

```json
{"jsonrpc":"2.0","id":"1","method":"v1.node.hello","params":{"node_id":"local"}}
{"jsonrpc":"2.0","id":"2","method":"v1.sandbox.create","params":{"node_id":"local","name":"demo","capability_token":"u1.…"}}
{"jsonrpc":"2.0","id":"3","method":"v1.exec.run","params":{"node_id":"local","sandbox_id":"sbx_l_…","cmd":["rg","--version"],"capability_token":"u1.…"}}
{"jsonrpc":"2.0","id":"4","method":"v1.fs.write","params":{"node_id":"local","sandbox_id":"sbx_l_…","path":"/work/a.txt","content":"hi","capability_token":"u1.…"}}
```

Every response carries `node_id`-scoped results; errors carry stable `ultraos_code` values
(`POLICY_DENIED`, `TOKEN_REQUIRED`, `APPROVAL_REQUIRED`, `HARD_DENY_UNAVAILABLE`, …).

## Invariants that have tests

- A **valid token cannot override a tier-2 rule** (`test_valid_token_cannot_override_hard_deny`).
- **Oracle down ⇒ everything state-changing is refused**, diagnostics still answer (`OracleDownTest`).
- Sandbox: no network, no host home, read-only `/usr`, `CapEff=0`, uid≠0, `mount`/`ptrace` EPERM
  (`tests/test_sandbox_isolation.py`, `proofs/`).
- **Tier-1 has no generic exec path**: interpreters, absolute paths, metacharacters and unknown
  flags are refused (`tests/test_hostapply.py`).
- Rules that change while the oracle runs stop it (`RuntimeFileWatchTest`); foreign uid on the
  oracle socket is refused (`PeerCredentialTest`).
- Every accepted/denied/critical request appends one audit record; edits, deletions and truncation
  are detected (`tests/test_audit.py`).
- No bare `except:` in `src/` — failures surface, they are not swallowed.

## Limitations (read before trusting it)

1. Audit is tamper-**evident**, not tamper-proof: same-uid (or root) can rewrite the chain.
2. Signing/approver keys are root-owned **in production only**; in this repo they sit in the
   operator's state dir. Until that moves, the oracle stops a jailbroken model, not a compromised
   account.
3. `app.install`, `host.apply`, `host.nix_profile` are contract-complete but return
   `-32008` with a milestone — no fake success, no silent stub.
4. Unprivileged `btrfs subvolume delete` needs `CAP_SYS_ADMIN`; replaced subvolumes are parked in
   `<state>/trash` and `snapshot.restore` reports `space_reclaim_needs_root`.
5. Containers share the kernel: microVM profile is phase 5. No GPU/display/dbus passthrough yet.

## Brand assets

`assets/` is empty on purpose — the mark is pending. Planned files: `parametral-mark.png`
(1024×1024), `parametral-lockup.png` (4:1), `favicon.ico`. Until they land, the hero renders as
type only; the `<img>` tag is commented out in the HTML block above.

## License

Not chosen yet. Code, policy files and generated proofs will get separate terms — policy and rules
are meant to be auditable and redistributable; the name and mark are not.
