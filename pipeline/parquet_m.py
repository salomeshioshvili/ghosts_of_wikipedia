"""Read dataset M with pyarrow.parquet only (no pyarrow.dataset / Acero, which some Windows
security policies block). Skips files and row groups whose page_id range can't match."""
import glob, os
from datetime import timezone

import pyarrow.parquet as pq

from common import DATA_M

_INDEX = None


def files():
    return sorted(glob.glob(os.path.join(DATA_M, "versions-*.parquet")))


def _index():
    """[(path, row_group, min_page_id, max_page_id)] from the Parquet statistics."""
    global _INDEX
    if _INDEX is None:
        _INDEX = []
        for path in files():
            pf = pq.ParquetFile(path)
            col = pf.schema_arrow.get_field_index("page_id")
            for i in range(pf.metadata.num_row_groups):
                stats = pf.metadata.row_group(i).column(col).statistics
                lo, hi = (stats.min, stats.max) if stats is not None and stats.has_min_max else (None, None)
                _INDEX.append((path, i, lo, hi))
    return _INDEX


def naive_utc(t):
    return t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def read_all(columns):
    """Every row of every file, selected columns only (for revisions.py)."""
    for path in files():
        yield from pq.ParquetFile(path).read(columns=columns).to_pylist()


def read_page(page_id, columns, batch_size=128):
    """Rows of one page, streamed in small batches (texts can be large)."""
    for path, rg, lo, hi in _index():
        if lo is not None and not (lo <= page_id <= hi):
            continue
        pf = pq.ParquetFile(path)
        cols = list(dict.fromkeys(["page_id", *columns]))
        for batch in pf.iter_batches(batch_size=batch_size, row_groups=[rg], columns=cols):
            ids = batch.column(0).to_pylist()
            if page_id not in ids:
                continue
            for row in batch.to_pylist():
                if row["page_id"] == page_id:
                    yield row
