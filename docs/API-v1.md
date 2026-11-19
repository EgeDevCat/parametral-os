# Parametral OS — Tool API, **v1**

Status: **FROZEN (v1.5.0)** — 2026-11-19  (v1.0.0 + host-tier methods; 1.1.1 pinned Ed25519 and the closed tier-1 presets; 1.2.0 implemented `snapshot.*`; 1.3.0 `app.*`; 1.4.0 implemented `host.apply`; 1.5.0 adds `net.*` grants; see §11)
Owner of this document: OS-layer team (this repo). Consumer: Parametral local AI (Berkay).
Change control: additive only, see §11.

---

## 1. Purpose and boundary

This document is the **only** contract between the AI (client) and the OS layer (server).
The AI never touches the host directly. Everything it does — running a command, reading a
file, installing an app, taking a snapshot, asking for a permission — is one JSON-RPC call
on this API. If a capability is not in this document, the AI does not have it.

The OS layer guarantees, for every request it accepts:

| Guarantee | Mechanism (implementation) |
|---|---|
| Runs isolated | bubblewrap namespaces (user, pid, net, ipc, uts, cgroup, mount) |
| Network closed by default | new net namespace, no interface up; opt-in `net.open` op |
| No host write access | host fs read-only binds only; sandbox has its own root |
| Never root | uid mapped 1:1, `--cap-drop ALL`, no setuid, `no_new_privs` |
| Bounded resources | cgroup v2 (`cpu.max`, `memory.max`, `pids.max`) + rlimits |
| Least privilege | capability token required per operation, TTL + use-count |
| Auditable | append-only, hash-chained audit log for every accepted call |
| Reversible | snapshot before mutation (phase 4) |

---

## 1.1 Security layers (three, not one)

| layer | what it is | failure mode | role |
|---|---|---|---|
| **GC Shield** | in-model training: 1.800 adversarial examples + DPO refusal training | probabilistic; can be jailbroken | *soft*: makes harmful intent less likely to be produced |
| **Hard-deny oracle** (`parametral-harddeny`) | separate deterministic process, **Ed25519-signed** read-only rule list (the oracle holds only the public key), tier 2 | no model in the loop: same input, same verdict | *hard*: disk tools, `/etc/shadow`, `/boot/**`, credential reads, host-mutating mounts → always refused, no approval offered |
| **Sandbox** | bubblewrap namespaces + seccomp + cgroups | kernel bug (out of scope until microVM) | *physical*: blast radius is one directory + one cgroup |

The AI's request path is: **oracle → policy → token → handler → audit**. The oracle
runs first and its denial is final. If the oracle is unreachable the gateway fails
closed (`-32013`), because "cannot check" must never mean "allowed".

GC Shield is never queried from here — it lives in the weights, it has no socket,
and it cannot be the thing that stops one command from destroying a disk.

### 1.2 Autonomy tiers

| tier | scope | gate | examples |
|---|---|---|---|
| **Tier 0 — sandbox / rootless** | anything inside a sandbox; `host.nix_profile` (rootless, generation rollback) | capability token auto-issued, **no human** | install/run/test apps, build, `nix profile install`, `home-manager switch` |
| **Tier 1 — real system write** | files in the real `$HOME`, `pacman -S`, system services, network open | **human approval** + pre-change snapshot + rollback handle | "kur şu paketi sisteme", firewall rule, service enable |
| **Tier 2 — never** | `hard_deny.v1.json` list | deterministic refusal, approval impossible | disk tools, `dd`, `modprobe`, `/etc/shadow`, `/boot/**`, `iptables` |

Tier 0 exists so autonomy is not strangled: routine work never waits for a human.
Tier 1 is where a human says yes once per real change. Tier 2 has no human override.

## 2. Transport

- **Protocol**: JSON-RPC 2.0, one JSON object per line (NDJSON framing, `\n` terminated, UTF-8).
- **Socket**: `AF_UNIX`, `SOCK_STREAM`
  - production: `/run/parametral/v1/control.sock`
  - per-user / development: `$XDG_RUNTIME_DIR/parametral/v1/control.sock`
  - override: env `PARAMETRAL_SOCKET`
- **Max request line**: 1 MiB (larger → `-32600`, connection closed).
- **Auth on the socket**: `SO_PEERCRED`; server rejects any peer whose uid != daemon uid
  (error `-32010 PEER_REJECTED`). No TCP listener exists in v1. No network auth exists in v1.
- **Concurrency**: requests on one connection are answered in order; a client MAY open
  several connections in parallel. Server is thread-per-connection.
- **Timeouts**: server-enforced per operation (see each method). Client should use ≥ that.

gRPC is intentionally **not** used: Unix-socket JSON-RPC keeps the dependency surface at zero
for both sides and survives hand-written clients. A gRPC facade can be generated later from
this same schema without breaking v1 clients.

---

## 3. Common envelope

Every request is a JSON-RPC 2.0 request. `params` **always** contains `node_id`
(node-ready design, §10) and may contain `capability_token`.

```json
{
  "jsonrpc": "2.0",
  "id": "req-0001",
  "method": "v1.exec.run",
  "params": {
    "node_id": "local",
    "capability_token": "u1.eyJ2IjoxLC...",
    "sandbox_id": "sbx_7f3a1c",
    "cmd": ["uname", "-r"],
    "timeout_s": 10
  }
}
```

Rules binding both sides:

1. `node_id` is **mandatory** on every request. `"local"` means "the node this socket belongs to".
   A non-matching node_id → `-32011 NODE_MISMATCH` (v1 daemon only knows its own id).
2. Unknown **params fields MUST be ignored** (forward compatibility).
3. Unknown **methods** → `-32601`. Methods are prefixed `v1.`; a `v2.` prefix is reserved.
4. All timestamps are RFC 3339 UTC with `Z`. All durations are seconds unless suffixed `_ms`.
5. Binary content is base64 (`content_b64`). Text content is UTF-8 (`content`).
6. Idempotency: mutating calls accept optional `idempotency_key` (string, ≤64 chars).
   Replaying the same key within 10 min returns the original result instead of re-executing.

### 3.1 Error object

```json
{"jsonrpc":"2.0","id":"req-0001","error":{"code":-32001,"message":"policy denied",
 "data":{"parametral_code":"POLICY_DENIED","rule_id":"default-deny","operation":"exec.run",
         "hint":"request a capability token via v1.permission.request"}}}
```

| code | parametral_code | meaning |
|---|---|---|
| -32700 | `PARSE_ERROR` | invalid JSON |
| -32600 | `INVALID_REQUEST` | envelope/params schema violation (`data.field` names the field) |
| -32601 | `METHOD_NOT_FOUND` | unknown method |
| -32602 | `INVALID_PARAMS` | field present but semantically invalid |
| -32603 | `INTERNAL` | server bug; `data.detail` present, audit record written |
| -32001 | `POLICY_DENIED` | policy said deny (default-deny path) |
| -32002 | `TOKEN_REQUIRED` | operation needs a capability token, none supplied |
| -32003 | `TOKEN_INVALID` | bad signature, expired, wrong node/op/scope, uses exhausted |
| -32004 | `APPROVAL_REQUIRED` | policy allows only with human approval; `data.approval_id` returned |
| -32005 | `APPROVAL_PENDING` | approval exists but not decided yet |
| -32006 | `NOT_FOUND` | sandbox/app/snapshot/approval id unknown |
| -32007 | `LIMIT_EXCEEDED` | quota, timeout, output cap, or path escape |
| -32008 | `UNSUPPORTED` | method reserved by this contract, not implemented yet; `data.milestone` |
| -32009 | `SANDBOX_UNAVAILABLE` | namespaces/cgroups unavailable on this host |
| -32010 | `PEER_REJECTED` | socket peer uid mismatch |
| -32011 | `NODE_MISMATCH` | node_id is not this daemon's node |
| -32012 | `CONFLICT` | duplicate name, sandbox busy, snapshot in progress |
| -32013 | `HARD_DENY_UNAVAILABLE` | tier-2 oracle unreachable → fail closed (no operation) |

---

## 4. Capability tokens

The AI **never** has root and never holds a long-lived credential. Every state-changing
operation needs a token issued by `v1.permission.request`.

Wire format (opaque to client, but documented so both sides can debug):

```
u1.<base64url(payload_json)>.<base64url(HMAC-SHA256(key, "u1."+b64payload))>
```

Payload:

```json
{
  "v": 1,
  "tid": "tok_01J8Z9K3",
  "node_id": "local",
  "ops": ["exec.run", "fs.read"],
  "scope": {"sandbox_ids": ["sbx_7f3a1c"], "paths": ["/work/**"], "commands": ["git", "npm"]},
  "iat": "2026-11-19T09:00:00Z",
  "exp": "2026-11-19T09:15:00Z",
  "max_uses": 25,
  "approval_id": null
}
```

Verification (server side, every request): signature valid → `v==1` → not expired →
`node_id` matches → requested op ∈ `ops` → request params ∈ `scope` → use count not exhausted.
Any failure is `-32003`. Uses are counted in the audit log and in daemon memory; tokens are
single-node and never transferable between nodes.

Token TTL is capped by policy (`max_ttl_s` per rule), never by the caller's wish.
A token whose `exp` is in the past is rejected even if its signature is valid.

---

## 5. Methods

### 5.0 Method index (all of v1)

| method | token op | status |
|---|---|---|
| `v1.node.hello` | — | implemented |
| `v1.node.status` | — | implemented |
| `v1.policy.explain` | — | implemented |
| `v1.permission.request` | — (grants) | implemented |
| `v1.sandbox.create` | `sandbox.create` | implemented |
| `v1.sandbox.list` | — | implemented |
| `v1.sandbox.status` | — | implemented |
| `v1.sandbox.destroy` | `sandbox.destroy` | implemented |
| `v1.exec.run` | `exec.run` | implemented |
| `v1.net.open` | `net.open` | implemented (allow-listed proxy, approval-gated) |
| `v1.net.close` | `net.close` | implemented |
| `v1.net.list` | `net.list` | implemented |
| `v1.fs.read` | `fs.read` | implemented |
| `v1.fs.write` | `fs.write` | implemented |
| `v1.fs.edit` | `fs.write` | implemented |
| `v1.fs.list` | `fs.read` | implemented |
| `v1.fs.delete` | `fs.write` | implemented |
| `v1.app.install` | `app.install` | implemented (source `nix`; approval-gated) |
| `v1.app.remove` | `app.remove` | implemented (approval-gated) |
| `v1.app.verify` | `app.read` | implemented (re-runs the manifest's verify step) |
| `v1.snapshot.create` | `snapshot.create` | implemented (btrfs, unprivileged) |
| `v1.snapshot.list` | `snapshot.list` | implemented |
| `v1.snapshot.restore` | `snapshot.restore` | implemented (approval + `confirm:true`) |
| `v1.approvals.list` | `approvals.read` | implemented |
| `v1.approvals.get` | `approvals.read` | implemented |
| `v1.approvals.decide` | `approvals.decide` + approver proof | implemented |
| `v1.audit.query` | `audit.read` | implemented |
| `v1.audit.verify` | — | implemented |
| `v1.host.nix_profile` | `host.nix_profile` | contract frozen, `-32008` (phase 2) |
| `v1.host.apply` | `host.apply` | implemented (signed job → sysapply as root) |
| `v1.node.peers` | — | reserved, `-32008` (phase 5) |
| `v1.node.dispatch` | — | reserved, `-32008` (phase 5) |
| `v1.snapshot.replicate` | — | reserved, `-32008` (phase 5) |

Conventions: `$sbx` = sandbox id, `$node` = node id. "Token op" column names the value that
must appear in the token's `ops` (plus scope match). `—` = no token needed (read-only, no
side effects).

### 5.1 `v1.node.hello`

Handshake + version negotiation. Must be the first call of a session.

```json
// params
{"node_id":"local","client_version":"ultra-si/0.1.0","protocol_versions":["v1"]}
// result
{"node_id":"local","server_version":"0.1.0","protocol_versions":["v1"],
 "selected":"v1","features":["sandbox.bwrap","seccomp.blacklist","cgroup.v2","audit.chain"],
 "policy_version":3,"started_at":"2026-11-19T08:59:00Z"}
```

Errors: `-32602` if `protocol_versions` has no common entry.

### 5.2 `v1.node.status` — no token

```json
// params
{"node_id":"local","include":["sandboxes","quotas","policy"]}
// result
{"node_id":"local","server_version":"0.1.0","uptime_s":812,
 "sandboxes":[{"sandbox_id":"sbx_7f3a1c","name":"demo","state":"running","execs":3}],
 "quota_backend":"cgroup2","limits_default":{"cpu_cores":1.0,"memory_mb":512,"pids":128},
 "policy_version":3,"audit":{"head_seq":114,"head_hash":"sha256:9a1c…","verified":true}}
```

`node_id` in the result is the addressed node — in a future swarm the same call is routed per
node, and this field is what disambiguates. v1 answers only for itself.

### 5.3 `v1.policy.explain` — no token

Dry-run of the policy engine; this is how the AI learns what it may do before trying.

```json
// params
{"node_id":"local","operation":"exec.run",
 "scope":{"sandbox_id":"sbx_7f3a1c","argv0":"curl","paths":["/work/x"]}}
// result
{"decision":"deny","rule_id":"default-deny","requires_approval":false,
 "reason":"no allow rule matched operation exec.run for argv0=curl",
 "max_ttl_s":null}
```

`decision` ∈ `allow | deny`. `requires_approval=true` means "allow only after human approval".

### 5.4 `v1.permission.request`

Exchanges a *justification* for a capability token. This is the only way to get a token.

```json
// params
{"node_id":"local","operation":"exec.run",
 "scope":{"sandbox_id":"sbx_7f3a1c","commands":["git"]},
 "ttl_s":600,"justification":"user asked to install ripgrep",
 "requested_by":"ultra-si/0.1.0"}
// result (policy allows without approval)
{"capability_token":"u1.…","expires_at":"2026-11-19T09:15:00Z","max_uses":25,
 "ops":["exec.run"],"scope":{…},"approval_id":null}
```

If policy requires approval, the call returns `-32004 APPROVAL_REQUIRED` with
`data.approval_id` and `data.expires_at`. The AI then (a) tells the user, (b) polls
`v1.approvals.get`, or (c) retries `v1.permission.request` with the same `justification` and
`approval_id` once approved, which returns the token. Never auto-approve: approval decision is
only accepted from a peer holding the `approver` role (see §7).

### 5.5 `v1.sandbox.create` — token op `sandbox.create`

```json
// params
{"node_id":"local","name":"ripgrep-demo","profile":"strict",
 "limits":{"cpu_cores":1.0,"memory_mb":512,"pids":128,"disk_mb":256},
 "net":false,
 "mounts":[{"host_path":"/opt/models","sandbox_path":"/models","mode":"ro"}],
 "env":{"LANG":"C.UTF-8"}}
// result
{"sandbox_id":"sbx_7f3a1c","name":"ripgrep-demo","state":"created",
 "root":"/var/lib/parametral/sandboxes/sbx_7f3a1c",
 "limits":{"cpu_cores":1.0,"memory_mb":512,"pids":128,"disk_mb":256},
 "net":false,"created_at":"2026-11-19T09:00:12Z",
 "cgroup":"/sys/fs/cgroup/parametral/sbx_7f3a1c"}
```

- `profile`: `strict` (default) | `net-client` (reserves a net namespace that `net.open` can
  later join; still closed until then) | `microvm` (**reserved, `-32008` until phase 5**).
- `mounts[]` are host paths the *operator* pre-approved in policy (`host_mounts` rule field);
  a mount not present in policy → `-32001`. The AI cannot invent host mounts.
- `disk_mb` is enforced by `RLIMIT_FSIZE` per file plus, from phase 4, btrfs qgroup; the
  reported `limits.disk_mb` is the effective value.
- Duplicate `name` → `-32012`.

### 5.6 `v1.sandbox.list` / `v1.sandbox.status` / `v1.sandbox.destroy` — no token / no token / token op `sandbox.destroy`

```json
// v1.sandbox.status
{"node_id":"local","sandbox_id":"sbx_7f3a1c"}
→ {"sandbox_id":"sbx_7f3a1c","name":"ripgrep-demo","state":"created","execs":3,
   "quota":{"cpu_cores":1.0,"memory_mb":512,"pids":128,"disk_mb":256},
   "usage":{"cpu_ns":120000000,"memory_peak_bytes":18464768,"pids_current":2}}

// v1.sandbox.destroy
{"node_id":"local","sandbox_id":"sbx_7f3a1c","purge":true}
→ {"sandbox_id":"sbx_7f3a1c","state":"destroyed","purged":true,"audit_ref":"aud_…"}
```

Destroy kills the cgroup (all pids), removes mounts, and (if `purge`) deletes the sandbox root.

### 5.7 `v1.exec.run` — token op `exec.run`

The only way to execute anything.

```json
// params
{"node_id":"local","sandbox_id":"sbx_7f3a1c",
 "cmd":["rg","--version"],"cwd":"/work","timeout_s":30,
 "env":{"TERM":"dumb"},"stdin_b64":null,"max_output_bytes":65536}
// result
{"exit_code":0,"stdout":"ripgrep 14.1.1\n","stderr":"","duration_ms":37,
 "truncated":false,"timed_out":false,"signaled":false,
 "seccomp_profile":"blacklist-v1","sandbox_id":"sbx_7f3a1c","audit_ref":"aud_…"}
```

- `cmd` is an **argv array**, never a shell string. Shell is available only as
  `["/bin/sh","-c", …]` and only if policy's `commands` scope allows `sh`.
- Default `timeout_s` 30, max 3600. On timeout: `timed_out:true`, `exit_code:124`, cgroup killed.
- `max_output_bytes` default 65536, max 4 MiB; exceeding sets `truncated:true`.
- `seccomp_profile` names the syscall policy in force; blocked syscalls surface to the app as
  `EPERM` (graceful degradation, not SIGSYS kill), so a denial shows up in the app's stderr.
- Non-zero exit code is **not** an error — it is data. Only transport/policy failures are errors.
- `env` is merged over a fixed base (`PATH`, `HOME`, `TERM`, `LANG`); the client cannot
  override `PATH` beyond policy's `commands` allowlist shadowing rules (v1: `PATH` is fixed).

### 5.8 Filesystem — `fs.read` / `fs.write` / `fs.edit` / `fs.list` / `fs.delete`
Token ops: `fs.read` (read/list), `fs.write` (write/edit/delete).

```json
// v1.fs.read
{"node_id":"local","sandbox_id":"sbx_7f3a1c","path":"/work/notes.txt","max_bytes":1048576}
→ {"path":"/work/notes.txt","content":"…","encoding":"utf-8","size":42,
   "sha256":"…","truncated":false}

// v1.fs.write
{"node_id":"local","sandbox_id":"sbx_7f3a1c","path":"/work/notes.txt",
 "content_b64":"aGVsbG8K","mode":"0644","create_parents":true}
→ {"path":"/work/notes.txt","size":6,"sha256":"…","created":true}

// v1.fs.edit  (exact-match replace; ambiguous match → error)
{"node_id":"local","sandbox_id":"sbx_7f3a1c","path":"/work/notes.txt",
 "old":"hello","new":"merhaba","count":1}
→ {"path":"/work/notes.txt","replacements":1,"sha256":"…"}

// v1.fs.list
{"node_id":"local","sandbox_id":"sbx_7f3a1c","path":"/work","recursive":false,"max_entries":500}
→ {"entries":[{"name":"notes.txt","type":"file","size":6,"mode":"0644","mtime":"…"}]}
```

Path rules: absolute, sandbox-internal; `..` escape, symlink escape, or access outside
`/work` and `/home/user` → `-32007 LIMIT_EXCEEDED` (escape is a *security* event, always audited
with `severity:"security"`). Reads > `max_bytes` are truncated, never error.

### 5.9 Application lifecycle — `app.install` / `app.remove` / `app.verify`
Token ops: `app.install`, `app.remove`, `app.read` (verify/status). **Implemented** for
`source:"nix"`; `source:"artifact"` answers `-32008` with `milestone:"phase-2b"`.

**Manifest v1** (validated before anything runs — no verify command, no install):

```json
{"name":"ripgrep","version":"14.1.1","source":"nix",
 "flake_ref":"nixpkgs#ripgrep",
 "flake_lock":"sha256-…",
 "verify":{"cmd":["rg","--version"],"expect_exit":0,"expect_stdout_contains":"ripgrep"},
 "permissions":{"network":["cache.nixos.org:443"],"write_dirs":["/work/appdata"],
                "ipc":["sbx_7f3a1c"]}}
```

- `name`: `[a-z0-9][a-z0-9._+-]{0,63}` · `flake_ref`: `nixpkgs#attr` or `github:o/r#attr`
- `flake_lock`: pinned hash (strings that look like `sha256-…` or 64 hex chars); the lock is
  recorded in the result so a later update is a decision, not a surprise.
- `verify` is **mandatory**: `cmd` (argv), `expect_exit` (default 0), optional
  `expect_stdout_contains`. An install nobody can check is refused with `-32602`.
- `permissions` declares what the app is allowed to use: `network` (host:port list),
  `write_dirs` (absolute, inside `/work`), `ipc` (sandbox ids). The pipeline records them and
  refuses malformed values; D5 wires them to the nftables rules.

Pipeline (each step observable in the result):

1. validate manifest → 2. `snapshot.create` (`pre-install-<name>`, when btrfs is available) →
3. `nix profile install` **inside the sandbox** with `--option builders ''`,
   `--option substituters https://cache.nixos.org`, `--option require-sigs true`
   (the store is read-only in the sandbox; writes go through the host `nix-daemon` socket) →
4. verify (real argv, real exit code) → 5. retry up to `attempt_limit` (max 3) →
6. report.

```json
{"app_id":"app_2b91","state":"installed","attempts":1,
 "verify":{"passed":true,"exit_code":0,"stdout_tail":"ripgrep 14.1.1\n"},
 "snapshot_id":"snap_…","flake_lock":"sha256-…","duration_ms":18422,
 "permissions":{"network":[],"write_dirs":["/work/appdata"],"ipc":[]},
 "failures":[],"diagnosis":null}
```

Failure is data, never silence: `state:"failed"`, `attempts` (≤3), `failures[]` with
`stage` (`install`/`verify`), `exit_code`, `timed_out`, and a ≤4 KiB `stderr_tail` per attempt,
plus a `diagnosis` string that names the likely cause (substituter unreachable, bad attribute,
signature rejected, or "install worked, verify fails"). `rollback` is
`nix profile rollback --profile /work/.nix-profile`; the pre-install snapshot is the second net.

### 5.10 Snapshots — `snapshot.create` / `snapshot.list` / `snapshot.restore`
Token ops: `snapshot.create`, `snapshot.list`, `snapshot.restore`. **Implemented** as read-only
btrfs subvolume snapshots of the sandbox root *and* home; no root needed to create, list or
restore. `snapshot.restore` also takes a `pre-restore-…` safety snapshot first, and requires
`confirm:true` plus an approval-gated token. If the state directory cannot host btrfs subvolumes
the daemon answers `-32008` with `data.milestone:"phase-4"` instead of pretending.

```json
// v1.snapshot.create
{"node_id":"local","label":"pre-install-ripgrep","reason":"app.install",
 "include_sandbox_id":"sbx_7f3a1c"}
→ {"snapshot_id":"snap_20261119T090154_ab12","created_at":"…","kind":"btrfs",
   "bytes_exclusive":18432000,"parent":"snap_20261119T085500_0f31"}

// v1.snapshot.restore
{"node_id":"local","snapshot_id":"snap_…","confirm":true,"dry_run":false}
→ {"restored":true,"from":"snap_…","pre_restore_snapshot":"snap_…(auto)","reboot_required":false}
```

`confirm:true` is mandatory (destructive). Policy makes `snapshot.restore` always
`requires_approval:true`. The result's `space_reclaim_needs_root` tells the caller whether old
subvolumes had to be parked (unprivileged `btrfs subvolume delete` needs `CAP_SYS_ADMIN` or the
`user_subvol_rm_allowed` mount option).

### 5.11 Approvals — `v1.approvals.list` / `v1.approvals.get` / `v1.approvals.decide`
`decide` requires the `approver` role (§7).

```json
// v1.approvals.decide
{"node_id":"local","approval_id":"apr_91c2","decision":"approve","reason":"ok, install it",
 "decided_by":"user:egedevcat"}
→ {"approval_id":"apr_91c2","state":"approved","decided_at":"…"}
```

`decision` ∈ `approve | reject | defer`. Pending approvals expire after 15 min → `expired`.

### 5.12 Audit — `v1.audit.query` / `v1.audit.verify`
Token: `audit.read` for query; `verify` needs none (read-only integrity check).

```json
// v1.audit.verify
{"node_id":"local","full":true}
→ {"verified":true,"records":114,"head_seq":114,"head_hash":"sha256:9a1c…",
   "first_broken_seq":null,"checked_at":"…"}

// v1.audit.query
{"node_id":"local","from_seq":100,"limit":50,"method":"v1.exec.run"}
→ {"records":[{"seq":114,"ts":"…","actor":"token:tok_01J8Z9K3","method":"v1.exec.run",
   "sandbox_id":"sbx_7f3a1c","result":"ok","token_id":"tok_01J8Z9K3","prev_hash":"…","hash":"…"}],
   "next_seq":115}
```

### 5.12b Off-host audit anchors (operator CLI, not a wire method)

`parametral audit anchor --out <dir>` appends `{seq, head_hash, created_at, sig}` to
`<dir>/anchors.jsonl`, signed with the operator key. `parametral audit anchor-verify --out <dir>`
returns `signatures_ok`, `chain_verified` and `chain_matches`; it fails when an anchor signature
does not verify, when the chain no longer verifies, or when the local record at the anchored seq
no longer hashes to the anchored value (rewritten/truncated log). Anchors are append-only and
safe to copy to a git repo, object storage or a log collector.

### 5.13 Reserved for phase 5 (contract present, `-32008` now)
`v1.node.peers`, `v1.node.dispatch`, `v1.snapshot.replicate`. **No swarm code exists in v1**
(by design); these names are reserved so v2 clients never see a method change meaning.

---

### 5.14 Host layers — `host.apply` (tier 1) and `host.nix_profile` (tier 0)

`host.apply` is **implemented** as a signed-job pipeline. `host.nix_profile` is still
contract-only (`-32008`, milestone `phase-2b`).

**Why a job and a signature:** the gateway runs as the service user and cannot sign. The exact
argv an approval covers is signed by the approver, then verified and executed by `sysapply`
(root). An unsigned job never runs, and "approved" plus "these argv" cannot drift apart.

```json
// 1) ask for the change (approval-gated token required)
{"node_id":"local","intent":"install system package ripgrep",
 "steps":[{"kind":"pacman","argv":["pacman","-S","--noconfirm","ripgrep"]}],
 "snapshot":true,"approval_id":"apr_…","wait_s":3}

// 2) queued → approver signs the exact payload
//    → {"error":{"code":-32005,"data":{"parametral_code":"APPROVAL_PENDING",
//         "job_id":"job_ab12…","how":"parametral host sign job_ab12…"}}}

// 3) collect the result
{"node_id":"local","job_id":"job_ab12…"}
→ {"job_id":"job_ab12…","state":"applied","approved_by":"ed25519:…",
   "snapshot_id":"snap_…","intent":"install system package ripgrep",
   "steps":[{"kind":"pacman-install","argv":[…],"exit_code":0,"duration_ms":9100,
             "stdout_tail":"…","stderr_tail":""}],
   "finished_at":"2026-11-19T…Z"}
```

Job payload (canonical JSON, that byte string is what gets signed):

```json
{"job_id":"job_…","node_id":"local","created_at":"…","approval_id":"apr_…",
 "intent":"…","snapshot":true,
 "steps":[{"kind":"pacman-install","argv":["pacman","-S","--noconfirm","ripgrep"]}]}
```

Rules enforced by `sysapply` before anything runs:

1. signature verifies against the **approver public key** (`/etc/parametral/keys/approver.pub`);
   the gateway holds no key that can produce it;
2. `payload_sha256` in the signature record matches the payload (hand-edited jobs are refused);
3. the payload re-validates against the closed preset list (`hostapply`): no interpreters, no
   absolute paths, no metacharacters, no unlisted flags;
4. a pre-change snapshot must succeed — no snapshot, no change;
5. steps run one by one with a fixed environment, `shell=False`, and a timeout; the result
   records `state` (`applied` / `failed` / `rejected`), per-step exit codes and output tails.

Failure semantics: `state:"rejected"` means nothing ran (`SIGNATURE_INVALID`,
`SNAPSHOT_FAILED`, validation error); `state:"failed"` means a step ran and returned non-zero —
the remaining steps are not executed and the snapshot id is returned for rollback.

### 5.15 Network grants — `net.open` / `net.list` / `net.close`
Token ops: `net.open` (approval-gated), `net.list`, `net.close`.

The sandbox has **no network stack** (`--unshare-net`: no interfaces, no DNS, `connect()`
fails everywhere). A grant does not change that. Instead it publishes *one Unix socket per
approved destination* inside the sandbox, and a host-side proxy forwards only to the exact
`host:port` pairs that were approved.

```json
// params
{"node_id":"local","sandbox_id":"sbx_l_…","ttl_s":300,
 "hosts":[{"host":"crates.io","port":443}]}
// result
{"grant_id":"net_9f2c1a4b7e","sandbox_id":"sbx_l_…",
 "hosts":[{"host":"crates.io","port":443}],
 "socket_dir":"/run/net",
 "sockets":["/run/net/net_9f2c1a4b7e-443.sock"],
 "expires_in_s":300,
 "note":"the sandbox has no network stack; these Unix sockets are the only way out …"}
```

Semantics the caller can rely on:

- `hosts` is the complete allow-list. The proxy refuses every other destination, and it
  resolves nothing on its own: `10.0.0.0/8`, `localhost` and metadata addresses are only
  reachable if the approver typed them.
- The grant dies at `expires_in_s` (max 600 s per policy). Expired grants are swept; their
  sockets disappear.
- `net.list` shows live grants, `net.close` revokes one immediately (sockets are unlinked).
- Every grant creation, connection and connection failure is an audit record
  (`netproxy.*`), including the destination that was actually used.
- A refused connection looks like a closed socket to the app — not a silent success.

What this is not: a full packet filter. nftables rules are generated for the target image
as a second, kernel-side belt; the allow-list enforcement that exists *today* is this proxy.

## 6. Sandbox execution profile (normative)

What `v1.exec.run` actually does — the AI may rely on each line:

1. `bubblewrap --unshare-all --die-with-parent --new-session`
   → new user, pid, net, ipc, uts, cgroup, mount namespaces. PID 1 is the guard process.
2. Mounts: `/usr` (ro), `/etc/{passwd,group,hosts,resolv.conf}` (ro, synthetic `/etc`),
   sandbox root at `/work` (rw), sandbox home at `/home/user` (rw), `/proc`, `/dev` (minimal),
   `/tmp` (tmpfs, 64 MiB, `nosuid,nodev`).
3. `--clearenv` + fixed base env. No host `$HOME`, no ssh agent, no display, no dbus, no
   `/run`, no `/sys`, no host `/proc`, no `/dev/kvm`, no `/dev/dri`.
4. `--cap-drop ALL`, `no_new_privs=1`, uid/gid unchanged (never 0).
5. `seccomp_guard` installs a syscall blacklist **with EPERM, not kill** (so apps degrade
   gracefully): `mount, umount2, pivot_root, chroot, ptrace, process_vm_*, kexec_*, bpf,
   perf_event_open, setns, unshare, init_module, finit_module, delete_module, swapon, swapoff,
   reboot, iopl, ioperm, acct, add_key, keyctl, userfaultfd, open_tree, move_mount, fsopen,
   fsconfig, fsmount, fspick, mount_setattr, pidfd_getfd, kcmp`.
6. cgroup v2: `cpu.max`, `memory.max`, `memory.swap.max=0`, `pids.max`; process moved into the
   cgroup right after spawn (before the exec'd program can fork).
7. rlimits: `RLIMIT_AS` (memory_mb), `RLIMIT_CPU` (timeout+5), `RLIMIT_FSIZE` (disk_mb),
   `RLIMIT_NPROC` (pids), `RLIMIT_CORE=0`.
8. No network: new net ns with only a down `lo`. Any `socket()`+`connect()` fails with
   `ENETUNREACH`/`EACCES`; DNS is absent (`/etc/resolv.conf` only bound when `net=true`).

---

## 7. Roles and peers

| role | who | allowed |
|---|---|---|
| `client` | Parametral AI process | everything except `approvals.decide` |
| `approver` | human UI (desktop app / `parametral` CLI) | `approvals.*`, `audit.query`, `status` |
| `operator` | root/sysadmin | policy file, token key, daemon lifecycle (not via API) |

Role is derived from the socket peer: the daemon's own uid + a per-role `SO_PEERCRED`
supplementary check (v1: `approver` requires the peer to be the active seat user and the
request to carry `approver_proof` = HMAC over `approval_id|decision|nonce` with the
approver key stored 0600 in the user's runtime dir). The AI cannot mint `approver` proof
because it never has that key — no root needed, no ambient authority.

---

## 8. Policy file (input to the engine, not part of the wire protocol)

`/etc/parametral/policy/policy.v1.json`, version-controlled in git (`policy/` in this repo).
`default` is **deny**. A rule:

```json
{"id":"ai-exec-in-sandbox","effect":"allow","priority":100,
 "operations":["exec.run","fs.read","fs.write","fs.edit","fs.list"],
 "sandbox_ids":["*"],"paths":["/work/**","/home/user/**"],
 "commands":["git","npm","rg","nix","pacman","sh"],"max_ttl_s":900,
 "requires_approval":false}
```

Evaluation: (0) **tier-2 oracle first** (`hard_deny.v1.json`, deterministic, signed, no
approval path) → (1) validate → (2) any matching `deny` rule with priority ≥ best allow wins →
(3) highest-priority matching allow → (4) no match → deny. Deny rules always beat allow rules
of equal priority. `requires_approval:true` downgrades an allow to "needs human".

---

## 9. Audit record (format is part of the contract)

One JSON object per line, append-only, hash-chained:

```json
{"seq":114,"ts":"2026-11-19T09:01:58.412Z","node_id":"local",
 "method":"v1.exec.run","actor":"token:tok_01J8Z9K3","token_id":"tok_01J8Z9K3",
 "approval_id":null,"sandbox_id":"sbx_7f3a1c","params_sha256":"…","result":"ok",
 "exit_code":0,"duration_ms":37,"detail":null,"severity":"info",
 "prev_hash":"sha256:9a1c…","hash":"sha256:4d7e…"}
```

`hash = SHA-256(canonical_json(record minus "hash"))`. Verification recomputes every link and
compares `seq` continuity. Any edit, deletion, or reordering is detectable — that is the
guarantee, not "root cannot touch it" (root always can; off-host anchoring is phase 5).
Every request that changed state, every denied request, and every approval writes a record.

---

## 10. Node-ready, not distributed

- Every request carries `node_id`; every response echoes it.
- `v1.node.status` is per-node; there is no aggregate/global state in v1.
- Sandbox ids are prefixed with the node short id (`local` → `sbx_l_…`) so an id is
  unambiguously routable later.
- Tokens are node-scoped (`node_id` in payload) and **must not** be replayed across nodes.
- No swarm, gossip, membership, or distributed scheduler code exists in v1. Adding it later
  must not change any v1 method signature — that is the entire point of reserving §5.13.

---

## 11. Versioning and compatibility rules

1. `v1` is frozen. **Additive only**: new optional params, new result fields, new methods,
   new error `data` fields.
2. Removing/renaming a field, changing a type, or changing semantics requires `v2.*`
   methods; `v1.*` keeps working for ≥ 12 months after `v2` ships.
3. Clients MUST ignore unknown result fields and unknown `data` fields.
4. Servers MUST ignore unknown params fields (except where documented as validated).
5. `features[]` from `v1.node.hello` is the negotiation channel for optional behavior.
6. This document is semantic-versioned: doc `1.5.0` ↔ `v1` wire (1.1.0 added the `host.*`
   methods and the oracle stage; 1.1.1 pinned Ed25519 signatures, the closed tier-1 preset list
   and the runtime rule-file watch; 1.2.0 implemented `snapshot.*`; 1.3.0 `app.*`; 1.4.0
   implemented `host.apply` with approver-signed jobs; 1.5.0 adds `net.*` grants. No existing
   signature has ever changed.) Any doc change bumps the
   patch and lands with a test in `tests/test_api_contract.py`.

---

## 12. Worked example (full install flow, target state after phase 4)

```
→ v1.node.hello
→ v1.sandbox.create      {name:"ripgrep-demo", profile:"strict", net:false}
→ v1.permission.request  {operation:"app.install", scope:{sandbox_id:…}, ttl_s:900}
→ v1.app.install         {manifest:{…,"verify":{…}}}
← {state:"installed", attempts:1, verify:{passed:true}}
→ v1.exec.run            {cmd:["rg","--version"]}          # proof it really works
→ v1.snapshot.create     {label:"post-install-ripgrep"}     # rollback point
```

Failure path (never silent): `app.verify` fails 3× → `state:"failed"`, `failures[]` with real
stderr, and `v1.snapshot.restore` of the pre-install snapshot is offered to the user.
