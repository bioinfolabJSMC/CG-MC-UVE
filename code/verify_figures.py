"""Verify figure numbering, raster equivalence, resolution, fonts, and hashes.

The report is saved beside the figures. Numerical results are read only.
"""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageChops
from matplotlib import font_manager
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
NAMES = [
    'Figure_1_raw_spectra', 'Figure_2_preprocessing_and_PLS',
    'Figure_3_prediction_error_paths', 'Figure_4_selected_channels',
    'Figure_5_analysis_workflow', 'Figure_S1_partition_audit',
    'Figure_S2_all_preprocessing', 'Figure_S3_calibration_error_paths',
    'Figure_S4_selected_feature_correlations', 'Figure_S5_wavelet_features',
    'Figure_S6_stochastic_variation', 'Figure_S7_wavelet_repeated_CV',
    'Graphical_abstract_1', 'Graphical_abstract_2', 'Graphical_abstract_3',
]


def main():
    fig_dir = ROOT / 'figures'
    assert {p.stem for p in fig_dir.glob('*.png')} == set(NAMES)
    rows = []
    for name in NAMES:
        paths = {ext: fig_dir / f'{name}.{ext}' for ext in ['png', 'tiff', 'pdf', 'svg']}
        assert all(p.exists() for p in paths.values())
        with Image.open(paths['png']) as png, Image.open(paths['tiff']) as tiff:
            for raster in [png, tiff]:
                assert all(abs(v - 300) < .02 for v in raster.info['dpi'])
            assert png.size == tiff.size
            same = ImageChops.difference(png.convert('RGB'), tiff.convert('RGB')).getbbox() is None
            assert same
            pixels = list(png.size)
            png_dpi = list(png.info['dpi'])
            tiff_dpi = [float(v) for v in tiff.info['dpi']]
        svg = paths['svg'].read_text(encoding='utf-8')
        assert 'Times New Roman' in svg
        pdf = PdfReader(paths['pdf'])
        pdf_fonts = sorted({str(v.get_object().get('/BaseFont')) for page in pdf.pages
            for v in page['/Resources'].get('/Font', {}).values()})
        assert all('TimesNewRoman' in font_name for font_name in pdf_fonts), pdf_fonts
        if name in ['Figure_5_analysis_workflow', 'Graphical_abstract_1',
                    'Graphical_abstract_2', 'Graphical_abstract_3']:
            assert all(term not in svg for term in ['WT-MC-UVE', 'WT-CG-MC-UVE', 'db4', 'DWT'])
        rows.append(dict(name=name, pixels=pixels, png_dpi=png_dpi, tiff_dpi=tiff_dpi,
            png_tiff_same_pixels=same, pdf_font_names=pdf_fonts,
            sha256={ext: hashlib.sha256(p.read_bytes()).hexdigest() for ext, p in paths.items()}))
    font = font_manager.findfont(font_manager.FontProperties(family='Times New Roman'),
        fallback_to_default=False)
    report = {'figure_count': 15, 'main': 5, 'supplementary': 7,
        'graphical_abstract_alternatives': 3, 'formats': ['png', 'tiff', 'pdf', 'svg'],
        'Times_New_Roman_resolved_to': font, 'all_raster_exports_300_dpi': True,
        'all_PNG_TIFF_pixels_identical': True, 'figures': rows}
    (fig_dir / 'figure_asset_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS: 15 figures; 60 exports; 300 dpi; identical PNG/TIFF pixels; Times New Roman; SHA256 hashes.')


if __name__ == '__main__':
    main()
