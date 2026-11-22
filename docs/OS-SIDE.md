# OS side: verifier (0.3) and weight pager (6.1)

Two prototypes that do not depend on a GPU and do not wait for the AI runtime.

## Verifier — patch → build → test (0.3)

`src/parametral/verifier.py` is the deterministic gate around a proposed patch:

1. copy the repository to a throwaway tree,
2. apply the patch with `git apply` (fallback `patch -p1`),
3. run `build`, then `test` as **argv lists** (never a shell),
4. repeat the attempt (`repeat`, default 2) and classify:
   - all pass → `passed`
   - none pass → `failed`
   - mixed → `flaky` (quarantined, never counted as a win).

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

Run:

```fish
bin/parametral-verify task.json
```

The result contains `status`, `deterministic`, both attempt logs, `patch_sha256`,
`toolchain`, `network_isolated` and `workdir` only when `--keep` is used.

## Weight pager — mmap blocks with a content-hashed audit (6.1)

`src/parametral/weightpager.py` serves one block at a time from a model shard:

- block size **256 MB** by default, **4 KiB aligned**;
- logical identity `block_id = (layer, part)`, while the manifest maps tensors to blocks;
- `mmap(O_RDONLY)` is the primary path; two processes share the same physical pages;
- **no O_DIRECT** (it deliberately throws away the page cache);
- `MADV_SEQUENTIAL` + two-block-ahead `MADV_WILLNEED`; `pread`/`posix_fadvise` is the measured fallback;
- hot/cold is two-tier: active-step blocks are pinned, the rest are LRU. On a model larger
  than RAM this cannot create capacity; the honest measurements are hit rate and page-in time.

Manifest (produced by the model loader; `build_manifest` exists only for synthetic tests):

```json
{
  "version": 1,
  "model": "cyankiwi/Qwen3-Coder-Next-AWQ-4bit",
  "block_size": 268435456,
  "shards": {"model-00001.safetensors": {"path": "model-00001.safetensors"}},
  "blocks": [
    {"block_id": "layer.0.part.0", "shard": "model-00001.safetensors",
     "offset": 0, "length": 268435456, "sha256": "sha256:...", "layer": "layer.0"}
  ],
  "tensors": {"model.layers.0.self_attn.q_proj.weight": ["layer.0.part.0"]}
}
```

Run:

```fish
bin/parametral-weight --manifest manifest.json --audit blockaudit.jsonl read layer.0.part.0 --req-id demo
bin/parametral-weight --manifest manifest.json prefetch layer.0.part.0 layer.0.part.1 --req-id demo
bin/parametral-weight --manifest manifest.json --audit blockaudit.jsonl audit-verify
```

Audit domain **`parametral-block-v1`**, events:

- `weight.block.read`: `block_id`, `shard`, `offset`, `len`, `resident`, `latency_ms`, `req_id`, `content_sha256`, `prev_hash`, `hash`
- `weight.block.evict`: same identity plus the reason
- `weight.pagein.batch`: `block_ids`, `bytes`, `latency_ms`, `req_id`

`content_sha256` is mandatory for reads: an audit record without it is refused, because a
replay that cannot prove which bytes were served is decoration. `MainAuditSink` forwards
the same events into the daemon's global audit chain (phase 6.3).

## Acceptance measurements

Tiny synthetic model (tests):

- page-in milliseconds per block and hot vs cold hit rate;
- two pagers in one process map the same shard; RSS sharing is an OS property, not a pager claim;
- `audit-verify` reports a valid chain, and a tampered record breaks it.

On the 9B AWQ (6.1 GB) and REAP-40B (22 GB) targets the same CSV/JSON counters are the
evidence: block latency, hit ratio, shared RSS, audit head.
