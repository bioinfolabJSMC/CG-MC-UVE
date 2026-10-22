"""Check the 38-main/3-supplement reference maps and package EndNote imports.

Bibliographic metadata is read only. The script writes a validation report and
an import archive; it does not claim to create a native EndNote database.
"""
from pathlib import Path
import csv
import hashlib
import json
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'references'


def csv_records(name):
    with (REF / name).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def main():
    library = json.loads((REF / 'references.json').read_text(encoding='utf-8'))
    records = {int(record['id']): record for record in library}
    assert len(records) == len(library) == 41
    assert set(records) == set(range(1, 42))
    main_map = csv_records('manuscript_citation_map.csv')
    supplement_map = csv_records('supplementary_citation_map.csv')
    assert [row['citation_number'] for row in main_map] == [str(i) for i in range(1, 39)]
    assert [row['citation_number'] for row in supplement_map] == ['S1', 'S2', 'S3']
    assert [int(row['record_id']) for row in supplement_map] == [26, 27, 28]
    all_ids = [int(row['record_id']) for row in main_map + supplement_map]
    assert len(all_ids) == len(set(all_ids)) == 41
    assert set(all_ids) == set(records)
    for row in main_map + supplement_map:
        record = records[int(row['record_id'])]
        assert row['title'] == record['title']
        assert row['doi'].lower() == record.get('doi', '').lower()
    metadata_names = ['references.json', 'EndNote_import.xml', 'references.ris']
    report = {
        'library_record_count': 41,
        'main_reference_count': 38,
        'supplementary_reference_count': 3,
        'main_citation_numbers': '1-38',
        'supplementary_citation_numbers': 'S1-S3',
        'supplementary_record_ids': [26, 27, 28],
        'all_library_records_mapped_once': True,
        'titles_and_DOIs_match_library': True,
        'native_endnote_library_created': False,
        'bibliographic_metadata_sha256': {
            name: hashlib.sha256((REF / name).read_bytes()).hexdigest()
            for name in metadata_names
        },
    }
    (REF / 'reference_numbering_validation.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    archive_path = ROOT / 'EndNote_import_library.zip'
    files = sorted(path for path in REF.iterdir() if path.is_file())
    with ZipFile(archive_path, 'w', compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname='references/' + path.name)
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for path in files:
            assert archive.read('references/' + path.name) == path.read_bytes()
    print('PASS: 38 main + 3 supplementary references partition all 41 library records; archive contents verified.')


if __name__ == '__main__':
    main()
