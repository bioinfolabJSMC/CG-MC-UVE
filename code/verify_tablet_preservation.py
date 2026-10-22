"""Verify preserved tablet artifacts and exact shared-table values after M5 revision."""
import argparse,csv,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'results'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot(folder):
    folder=Path(folder)
    artifacts={p.name:sha(p) for p in sorted(folder.glob('tablet_*')) if p.is_file()}
    tables={}
    for path in sorted(folder.glob('*.csv')):
        with path.open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f)
            if not reader.fieldnames or 'dataset' not in reader.fieldnames:continue
            rows=[r for r in reader if r.get('dataset')=='tablet']
            if rows:tables[path.name]=dict(columns=reader.fieldnames,rows=rows)
    return dict(dataset='tablet',source_revision='revision_03',artifacts_sha256=artifacts,shared_csv_tables=tables)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--create-baseline',type=Path,help='Record a trusted prior results directory; ordinary verification needs no external files.')
    args=parser.parse_args()
    baseline_path=RES/'tablet_preservation_baseline.json'
    if args.create_baseline:
        if baseline_path.exists():raise FileExistsError('Baseline already exists; do not silently replace it.')
        baseline_path.write_text(json.dumps(snapshot(args.create_baseline),indent=2),encoding='utf-8')
    baseline=json.loads(baseline_path.read_text(encoding='utf-8'));current=snapshot(RES)
    artifacts={name:current['artifacts_sha256'].get(name)==digest for name,digest in baseline['artifacts_sha256'].items()}
    tables={name:current['shared_csv_tables'].get(name)==table for name,table in baseline['shared_csv_tables'].items()}
    report=dict(baseline='tablet_preservation_baseline.json',dataset='tablet',artifact_count=len(artifacts),shared_csv_count=len(tables),shared_csv_row_count=sum(len(t['rows']) for t in baseline['shared_csv_tables'].values()),artifact_sha256_matches=artifacts,shared_table_rows_exact_matches=tables,all_tablet_artifacts_byte_identical=all(artifacts.values()),all_tablet_shared_cells_exact=all(tables.values()))
    (RES/'tablet_preservation_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert all(artifacts.values()),[name for name,ok in artifacts.items() if not ok]
    assert all(tables.values()),[name for name,ok in tables.items() if not ok]
    print(f'PASS: {len(artifacts)} tablet artifacts byte-identical; {len(tables)} shared CSV tables preserve {report["shared_csv_row_count"]} tablet rows exactly.')

if __name__=='__main__':main()
