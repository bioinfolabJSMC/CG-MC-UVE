"""Verify that the editorial revision preserves all computational result bytes.

Ordinary verification is portable: the included baseline contains file sizes and
SHA-256 hashes and does not require the previous revision directory.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'results'
BASELINE_NAME = 'results_preservation_baseline.json'
REPORT_NAME = 'results_preservation_check.json'
# These are presentation/audit metadata, never model or numerical result files.
EXCLUDED_NAMES = {
    'document_audit.json',
    'figure_asset_audit.json',
    'figure_visual_QA.txt',
    BASELINE_NAME,
    REPORT_NAME,
    'non_wt_reporting_audit.json',
}


def snapshot(folder):
    folder = Path(folder)
    result = {}
    for path in sorted(folder.rglob('*')):
        if path.is_file() and path.name not in EXCLUDED_NAMES:
            content = path.read_bytes()
            result[path.relative_to(folder).as_posix()] = {
                'bytes': len(content),
                'sha256': hashlib.sha256(content).hexdigest(),
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create-baseline', type=Path,
                        help='Trusted revision_04 results directory; only for the first baseline creation.')
    args = parser.parse_args()
    baseline_path = RES / BASELINE_NAME
    if args.create_baseline:
        if baseline_path.exists():
            raise FileExistsError('The baseline already exists; it must not be silently replaced.')
        if not args.create_baseline.is_dir():
            raise NotADirectoryError(args.create_baseline)
        baseline = {
            'schema_version': 1,
            'source_revision': 'revision_04',
            'scope': 'Every computational result file; comparison is byte-for-byte, not rounded numerical equality.',
            'excluded_metadata_names': sorted(EXCLUDED_NAMES),
            'files': snapshot(args.create_baseline),
        }
        if not baseline['files']:
            raise ValueError('Refusing to create an empty preservation baseline.')
        baseline_path.write_text(json.dumps(baseline, indent=2) + '\n', encoding='utf-8')
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    expected = baseline['files']
    current = snapshot(RES)
    missing = sorted(set(expected) - set(current))
    unexpected = sorted(set(current) - set(expected))
    checks = {name: current.get(name) == record for name, record in expected.items()}
    changed = [name for name, equal in checks.items() if not equal and name not in missing]
    passed = not missing and not unexpected and not changed
    report = {
        'baseline': BASELINE_NAME,
        'source_revision': baseline['source_revision'],
        'expected_file_count': len(expected),
        'expected_bytes': sum(record['bytes'] for record in expected.values()),
        'missing_files': missing,
        'unexpected_computational_files': unexpected,
        'changed_files': changed,
        'file_bytes_and_sha256_match': checks,
        'all_computational_results_byte_identical': passed,
        'analysis_recomputed_in_editorial_revision': False,
    }
    (RES / REPORT_NAME).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not passed:
        raise SystemExit(f'FAIL: missing={missing}, changed={changed}, unexpected={unexpected}')
    print(f'PASS: all {len(expected)} computational result files are byte-identical to revision_04.')


if __name__ == '__main__':
    main()
