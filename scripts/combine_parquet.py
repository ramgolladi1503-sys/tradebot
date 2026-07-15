import pyarrow.parquet as pq
import pyarrow as pa
import glob
import sys

def combine_parquet_files(directory, output_file):
    files = sorted(glob.glob(f"{directory}/ticks_*.parquet"))
    if not files:
        print("No files found!")
        return
    
    print(f"Reading {len(files)} files...")
    tables = []
    for f in files:
        tables.append(pq.read_table(f))
        
    print("Concatenating tables...")
    combined_table = pa.concat_tables(tables)
    
    print(f"Writing {combined_table.num_rows} total rows to {output_file}...")
    pq.write_table(combined_table, output_file)
    print("Done!")
    
if __name__ == "__main__":
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
    
    combine_parquet_files(f"runtime/market_data/upstox/{date_str}", f"runtime/market_data/upstox/{date_str}/combined.parquet")
