"""Native Vortex/Parquet benchmark; deterministic non-sensitive synthetic test data.

State contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
A format is not rankable if any step fails. This CI test does not replace
the 1,876-row user research catalogue benchmark distributed separately.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

import brotli
import pyarrow as pa
import pyarrow.parquet as pq
import vortex as vx
import vortex.expr as ve

OUT = Path("web_atomic_native_results")
OUT.mkdir(exist_ok=True)
ROWS = [
    {"record_id":f"atom_{i:07d}", "kind":("HTML", "SVG", "MathML", "JSON")[i % 4],
     "element":("div", "path", "mfrac", "object", "span")[i % 5],
     "algorithm":("tree", "dictionary", "delta")[i % 3], "metric":str(i % 101)}
    for i in range(1876)
]
COLS = list(ROWS[0])
TARGET = ROWS[len(ROWS)//2]["record_id"]
FORMATS = ("column_json_brotli", "parquet_zstd", "vortex_default", "vortex_compact")
OPS = ("full_read", "one_column", "id_lookup")


def logical_hash(rows, cols):
    values = [[r[c] for c in cols] for r in rows]
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def store(fmt, path):
    if fmt == "column_json_brotli":
        cols = {c: [row[c] for row in ROWS] for c in COLS}
        path.write_bytes(brotli.compress(json.dumps(cols, separators=(",", ":")).encode(), quality=5))
    elif fmt == "parquet_zstd":
        pq.write_table(pa.table({c:pa.array([r[c] for r in ROWS],type=pa.string()) for c in COLS}),
                       str(path), compression="zstd", use_dictionary=True)
    else:
        array = vx.array(ROWS)
        if fmt == "vortex_default":
            vx.io.write(array, str(path))
        else:
            vx.io.VortexWriteOptions.compact().write(array, str(path))


def load(fmt, path, op):
    if fmt == "column_json_brotli":
        cols = json.loads(brotli.decompress(path.read_bytes()))
        indices = range(len(ROWS))
        if op == "id_lookup":
            indices = (i for i, x in enumerate(cols["record_id"]) if x == TARGET)
        keys = ["record_id"] if op == "one_column" else COLS
        return [{c:cols[c][i] for c in keys} for i in indices]
    if fmt == "parquet_zstd":
        return pq.read_table(str(path), columns=["record_id"] if op == "one_column" else None,
                             filters=[("record_id", "==", TARGET)] if op == "id_lookup" else None).to_pylist()
    handle = vx.open(str(path))
    projection = ["record_id"] if op == "one_column" else None
    expr = (ve.column("record_id") == TARGET) if op == "id_lookup" else None
    return handle.scan(projection, expr=expr).read_all().to_pylist()


def measure(fn):
    for _ in range(3):
        fn()
    values=[]
    for _ in range(12):
        t=time.perf_counter_ns()
        fn()
        values.append((time.perf_counter_ns()-t)/1e6)
    return round(statistics.median(values), 6)


records = []
failure = False
for fmt in FORMATS:
    entry={"format":fmt, "input_type":"deterministic_synthetic", "rows":len(ROWS),
           "state":"DISCOVERED", "bytes":None, "write_ms":None, "error":""}
    try:
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/("data."+fmt)
            start=time.perf_counter_ns()
            store(fmt, path)
            entry["write_ms"]=round((time.perf_counter_ns()-start)/1e6,6)
            entry["bytes"]=path.stat().st_size
            entry["state"]="ENCODED"
            assert logical_hash(load(fmt,path,"full_read"),COLS)==logical_hash(ROWS,COLS)
            entry["state"]="ROUNDTRIP_VERIFIED"
            for op in OPS:
                expect = ROWS if op=="full_read" else (
                    [{"record_id":r["record_id"]} for r in ROWS] if op=="one_column" else
                    [r for r in ROWS if r["record_id"]==TARGET])
                cols = ["record_id"] if op=="one_column" else COLS
                assert logical_hash(load(fmt,path,op),cols)==logical_hash(expect,cols)
                entry[op+"_median_ms"]=measure(lambda:load(fmt,path,op))
            entry["state"]="BENCHMARKED"
    except Exception as e:
        failure=True
        entry["state"]="FAILED"
        entry["error"]=type(e).__name__+": "+str(e)
    records.append(entry)
    print(json.dumps(entry))
metadata={"python":sys.version,"platform":platform.platform(),"pyarrow":pa.__version__,
          "vortex":getattr(vx,"__version__","unreported"),"input_sha256":logical_hash(ROWS,COLS),
          "repeats":12,"warmups":3}
(OUT/"environment.json").write_text(json.dumps(metadata,indent=2))
(OUT/"measurements.json").write_text(json.dumps(records,indent=2))
with (OUT/"measurements.tsv").open("w") as fp:
    keys=["format","input_type","rows","state","bytes","write_ms","full_read_median_ms",
          "one_column_median_ms","id_lookup_median_ms","error"]
    fp.write("\t".join(keys)+"\n")
    for rec in records:
        fp.write("\t".join(str(rec.get(k,"")) for k in keys)+"\n")
sys.exit(1 if failure else 0)
