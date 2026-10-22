"""Package the checked revision without changing scientific results."""
from pathlib import Path
import csv
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ['Manuscript', 'Supplementary', 'Highlights', 'Cover_letter', 'Graphical_abstracts']


def eligible(path):
    return (path.is_file() and path.suffix.lower() not in {'.zip', '.pyc'}
            and '__pycache__' not in path.parts and path.name != 'SHA256_manifest.csv')


def archive(name, files):
    target = ROOT / name
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
        for path in files:
            stream.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as stream:
        assert stream.testzip() is None, name
        assert len(stream.namelist()) == len(files), name
    return {'name': name, 'files': len(files), 'bytes': target.stat().st_size,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'integrity': 'PASS'}


def main():
    assert all((ROOT / (name + ext)).exists()
               for name in DOCUMENTS for ext in ['.docx', '.pdf'])
    assert (ROOT / 'audits/document_audit.json').exists()
    assert len(list((ROOT / 'figures').glob('*.png'))) == 15
    files = sorted(path for path in ROOT.rglob('*') if eligible(path))
    with (ROOT / 'SHA256_manifest.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['file', 'bytes', 'sha256'])
        for path in files:
            writer.writerow([path.relative_to(ROOT).as_posix(), path.stat().st_size,
                             hashlib.sha256(path.read_bytes()).hexdigest()])
    program = [path for path in files if path.relative_to(ROOT).parts[0]
               in {'code', 'data', 'results', 'references', 'audits'} or path.name.startswith('README')]
    graphics = [path for path in files if path.name.startswith('Graphical_abstract')]
    report = [archive('Complete_program.zip', program),
              archive('Graphical_abstracts_3_options.zip', graphics),
              archive('Submission_package.zip', files + [ROOT / 'SHA256_manifest.csv'])]
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
