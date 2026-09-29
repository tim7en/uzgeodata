# SR-01 deep dive: release provenance (2026-09-29 UTC)

## Finding

**Confirmed on the local checkout and public endpoint.** The pinned release `uz-20260924T150158900Z` describes a cube index with 27,874,080 rows. The current local and served index describes a September 28 rebuild with 28,856,820 rows, a difference of 982,740 rows. The public `latest.json` still names the September 24 release. The served old manifest still has the September 24 content. Thus the live fixed path `/data/atlas/cube/index.json` no longer represents the release to which the public pointer refers. This is a provenance failure; the numerical correctness of the new cube was not assessed.

Python's CA bundle on this machine rejected the HTTPS chain with `CERTIFICATE_VERIFY_FAILED: certificate has expired`. Windows Schannel verified the site with `curl.exe` and returned the same bytes. The leaf certificate for `uzgeodata.uz` is valid September 24–December 23, 2026. This is a client-specific Python trust-chain issue, not evidence of an expired portal certificate.

## Evidence and causal trace

1. `PUBLISHED/data/atlas/latest.json` and the release manifest were last committed in `06ac19791` on September 24. The manifest records `cube/index.json` as 17,212 bytes, SHA-256 `6f3c36818ef1e2108994e4a6958c8d87af6857fff0f6cfd59e39a7bd6edc8d6c`.
2. The September 24 Git blob is 16,812 bytes with LF line endings. Converting only its line endings to CRLF yields exactly 17,212 bytes and the manifest SHA-256. Thus the pinned manifest matches the index as it existed at release cut time; it is not simply a stale or arbitrary hash. This also shows that byte validation is sensitive to checkout line endings.
3. Commit `d9e3d917d` on September 28 replaced the tracked cube index with the TerraClimate v1.1 rebuild, raising its declared rows from 27,874,080 to 28,856,820 and indexed cube bytes from 164,838,610 to 185,790,167. The working index is 17,435 bytes, SHA-256 `08a51a3ce4fcd8f7525cdb5164b6a48d9d7e3da630e14e9bdc909c5c4f2a18b2`. Eleven of 14 locally present Parquet paths have sizes differing from the old manifest. No new atlas release pointer or release manifest accompanied the rebuild.
4. Four public GETs at 2026-09-29 12:47 UTC returned 200 using Windows Schannel TLS verification. The served pointer has the same semantic JSON as the local old pointer, and the served old manifest has the same semantic JSON as the local old manifest. The served cube index has the same semantic JSON as the current local index. The build deliberately compacts JSON, so served raw byte hashes differ from local raw byte hashes. Canonical parsed JSON hashes establish those equality claims.
5. `/release.json` reports frontend commit `b51a06b32cd54995b62309f730cca1b489c10782`, generated September 29. This is a frontend build identity; it is not the atlas release ID. The R2 publisher syncs `dist/data` objects by fixed key and can replace them independently of `latest.json`. `publish_release.py` records hashes but explicitly does not copy immutable artifacts. This design allows old release manifests to outlive their underlying fixed-path bytes.

| Artifact | Raw bytes / SHA-256 | Canonical JSON SHA-256 | Key content |
| --- | --- | --- | --- |
| Local September 24 manifest expectation for cube index | 17,212 / `6f3c3681…6edc8d6c` | n/a | 27,874,080 rows |
| September 24 Git index after CRLF conversion | 17,212 / `6f3c3681…6edc8d6c` | `d38b1b11…c0bcd72` | old cube |
| Current local cube index | 17,435 / `08a51a3c…5c4f2a18b2` | `f292132b…59a409` | 28,856,820 rows |
| Served cube index (verified TLS; compact JSON) | 13,878 / `5bd30e19…0f51223` | `f292132b…59a409` | current cube |
| Served latest pointer (verified TLS; compact JSON) | 385 / `1b95ac28…a264` | `17f442ab…ed16b` | old release |
| Served old manifest (verified TLS; compact JSON) | 16,159 / `aa2fbfc3…89c3f00` | `ac6c8f13…5edcbe5` | old release |

Full hashes, timestamps, HTTP statuses and metadata are in [evidence.json](evidence.json). The runnable probe is [probe.py](probe.py).

## Reproduce

From repository root:

```powershell
python -m qa.release_integrity --release-id uz-20260924T150158900Z --file cube/index.json
python qa/deep_dive/release/probe.py
git log -2 --format="%h %ad %s" --date=iso -- PUBLISHED/data/atlas/cube/index.json
git diff 06ac19791 d9e3d917d -- PUBLISHED/data/atlas/cube/index.json
```

The first command exits 1 with the local mismatch. The probe makes four bounded GET requests and persists only digests and selected JSON fields, never remote response bodies.

## Risk and safe remedy

An analysis citing the September 24 release ID can fetch current index and potentially current partition bytes from fixed URLs. A manifest check will detect changed bytes, but readers who do not verify hashes can unknowingly mix versions. The newer cube itself may be valid; the current evidence does not establish that. We did not hash public Parquet partitions, so their exact served versions remain unknown.

First, preserve the current old manifest and collect a complete, internally consistent snapshot of the current local cube and all indexed Parquet partitions. Validate all files, source versions, row counts and scientifically relevant derived products before cutting a **new** release manifest. Publish its content and verify served bytes before moving the default pointer. Do not edit the old manifest to match newer files. If the intended public state is instead the September 24 release, restore *all* old cube files from a verified archival snapshot, not just its index. Long term, use release-qualified immutable object keys and a single pointer promotion after upload verification; make CI and publication refuse a pointer whose manifest fails against the exact served bytes. Add a post-publication check because `build_launch.mjs` compacts JSON and therefore its raw served hash is expected to differ from the pre-build local hash unless hashes are calculated over the deployed representation.

Investigate this machine's Python CA bundle if Python HTTPS clients must access the portal. The public evidence here was collected through normally verified Windows Schannel. No published data, production code or release pointer was modified during this investigation.
