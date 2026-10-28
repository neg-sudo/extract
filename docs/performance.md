# Performance

## Measuring honestly

Use the bundled benchmark harness:

```bash
python3 scripts/benchmark.py --size-mb 10 --files 1000
python3 scripts/benchmark.py --size-mb 100 --files 10000
python3 scripts/benchmark.py --size-mb 1024 --files 100000 --keep
```

It generates ZIP and TAR.GZ fixtures, extracts them with the native pipeline,
and reports wall time, throughput, and files per second. Run it on the same
machine and filesystem you care about; numbers from another host are not
comparable.

## What is fast

* Native ZIP/TAR streaming avoids spawning external processes.
* GZIP/BZIP2/XZ use the CPython C accelerators (`zlib`, `bz2`, `lzma`).
* Validation is a single metadata pass, not a full re-read.
* External formats pay for one extra copy from the temp directory; this is the
  price of confinement and is deliberate.

## What is intentionally not optimised

* Parallel extraction **within one archive**. It complicates bomb accounting
  and safe writes; `--parallel` parallelises multiple archives instead.
* Memory mapping huge archives. Streaming keeps memory bounded.

## Notes on limits

Metadata checks happen before writes, so a rejected bomb costs only the time to
read the central directory or tar headers. Ratio checks are only enforced above
64 MiB of declared output to avoid false positives on tiny, highly compressible
files.

## Sample output

The shape of the report is:

```
format      files     bytes        seconds    MiB/s    files/s
zip          1000      10.00 MiB    0.031      322.6    32258
tar.gz       1000      10.00 MiB    0.118      84.7     8474
```

Treat this as a template, not a published benchmark. Real results depend on
compression level, storage, and CPU.
