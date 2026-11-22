# OS side: verifier (0.3) and weight pager (6.1)

Two prototypes that do not depend on a GPU and do not wait for the AI runtime.

## Verifier — patch → build → test (0.3)

`src/parametral/verifier.py` is the deterministic gate around a proposed patch:

1. copy the repository to a throwaway tree,
2. apply the patch with `git apply` (fallback `patch -p1`),
3. run `build`, then `test` as **argv lists** (never a shell),
4. apply the gate rule:
   - a **passing** task is not repeated (one build/test),
   - a **failing** task is repeated once; if the second run passes it is `flaky`
     and quarantined, otherwise `failed`.

Repeating every pass doubles build time; the dangerous error is a false pass, so the
repeat budget belongs to the failures.

Determinism inputs:

| input | value |
|---|---|
| locale | `LC_ALL=C`, `LANG=C` |
| timezone | `TZ=UTC` |
| clock | `SOURCE_DATE_EPOCH` (default 2026-11-21T00:00:00Z) |
| seed | `PYTHONHASHSEED` / `PARAMETRAL_SEED` |
| toolchain | `toolchain` map: binary name → SHA-256; mismatch is `TOOLCHAIN_MISMATCH` |
| network | `bwrap --unshare-all` when `bwrap` is installed; `network_isolated` is reported honestly |
| tests | run with the work tree mounted read-only (`--ro-bind work work`) |

Task JSON:

```json
{
  "task_id": "ue5-fix-0001",
  "repo": "/path/to/repo",
  "patch": "diff --git ...",
  "build": ["cmake", "--build", "build"],
  "test": ["ctest", "--output-on-failure"],
  "timeout_s": 300,
  "repeat": 2,
  "seed": 0,
  "toolchain": {"cmake": "<sha256 of /usr/bin/cmake>"},
  "env": {"CC": "clang"},
  "sandbox": "auto"
}
```

Single task:

```fish
bin/parametral-verify task.json
```

Batch (one JSON result per line, process stays alive, **exit code is always 0**;
the verdict is in the JSON):

```fish
bin/parametral-verify --batch tasks.jsonl
```

Result schema (stable keys):

```json
{
  "task_id": "ue5-fix-0001",
  "verdict": "passed",
  "exit_code": 0,
  "build_log_sha256": "...",
  "test_log_sha256": "...",
  "patch_sha256": "...",
  "toolchain_sha256": "sha256:...",
  "duration_ms": 1234,
  "flaky": false
}
```

The detailed `attempts`, `network_isolated`, `seed`, `epoch` and optional `workdir`
remain in the same object.

## Weight pager — mmap blocks with a content-hashed audit (6.1)

`src/parametral/weightpager.py` serves one block at a time from a model shard:

- block target **256 MB**, **4 KiB aligned**; a block never cuts a tensor;
- logical identity `block_id = (layer, part)`, with tensor→block metadata;
- `mmap(O_RDONLY)` is the primary path; two processes share the same physical pages;
- **no O_DIRECT** (it deliberately throws away the page cache);
- `MADV_SEQUENTIAL` + two-block-ahead `MADV_WILLNEED`; `pread`/`posix_fadvise` is the measured fallback;
- hot/cold is two-tier: active-step blocks are pinned, the rest are LRU;
- **hash once per cold page-in** and persist `(block_id, shard, size, mtime_ns, hash)`
  in `HashCache`. Warm reads reuse the hash. A 48 GB step must not spend 24–120 s
  re-hashing bytes that are already verified.
- the hash is taken over the **mmap region**; the pager never reads a block a second time
  with `pread`.
- `sha256` is the default; `hash_algo: "blake3"` is accepted when the optional `blake3`
  module is installed (the audit domain and `content_sha256` field stay the same).

### Tensor-aligned blocks

`build_manifest_from_safetensors` parses the shard header (8-byte length + JSON),
groups whole tensors up to the target size, and lets a single larger tensor stand alone.
The physical offset is rounded down/up to 4 KiB, so one block may include a few leading
bytes; the tensor offsets remain in the safetensors header. `build_manifest` is only a
synthetic benchmark helper and must not be used for a real checkpoint.

Manifest:

```json
{
  "version": 1,
  "model": "cyankiwi/Qwen3-Coder-Next-AWQ-4bit",
  "block_size": 268435456,
  "hash_algo": "sha256",
  "shards": {"model-00001.safetensors": {"path": "model-00001.safetensors"}},
  "blocks": [
    {"block_id": "layer.block.00000", "shard": "model-00001.safetensors",
     "offset": 0, "length": 268435456, "sha256": "sha256:...", "layer": "layer.0"}
  ],
  "tensors": {"model.layers.0.self_attn.q_proj.weight": ["layer.block.00000"]}
}
```

Run:

```fish
bin/parametral-weight --manifest manifest.json --audit blockaudit.jsonl --hash-cache hashcache.json read layer.block.00000 --req-id demo
bin/parametral-weight --manifest manifest.json prefetch layer.block.00000 layer.block.00001 --req-id demo
bin/parametral-weight --manifest manifest.json --audit blockaudit.jsonl audit-verify
```

Audit domain **`parametral-block-v1`**, events:

- `weight.block.read`: `block_id`, `shard`, `offset`, `len`, `resident`, `latency_ms`, `req_id`, `content_sha256`, `prev_hash`, `hash`
- `weight.block.evict`: same identity plus the reason
- `weight.pagein.batch`: `block_ids`, `bytes`, `latency_ms`, `req_id`

`content_sha256` is mandatory for reads: an audit record without it is refused, because a
replay that cannot prove which bytes were served is decoration. `MainAuditSink` forwards
the same events into the daemon's global audit chain (phase 6.3).

## Tiny measurement (this machine)

`scripts/bench_weightpager.py` on a 128 MB synthetic shard, 16 MB blocks, 8 blocks:

| metric | value |
|---|---|
| cold page-in / block | **13.9 ms** mean (median 14.3, max 14.5) |
| hot read / block | **0.037 ms** mean (zero-copy view) |
| cold sequential | **1152 MB/s** |
| hot sequential | **362910 MB/s** (page cache) |
| RSS, second pager | **+0 KB** (shared mmap pages) |
| audit | 24 records, chain valid |

These are synthetic numbers, not the 9B acceptance: they verify the mechanism and the
shared-page claim. The 9B AWQ (6.1 GB) and REAP-40B (22 GB) runs must repeat the same
JSON fields on real shards.

## Acceptance measurements

Tiny synthetic model (tests):

- page-in milliseconds per block and hot vs cold hit rate;
- two pagers in one process map the same shard; RSS sharing is an OS property, not a pager claim;
- `audit-verify` reports a valid chain, and a tampered record breaks it.

On the 9B AWQ (6.1 GB) and REAP-40B (22 GB) targets the same CSV/JSON counters are the
evidence: block latency, hit ratio, shared RSS, audit head.
