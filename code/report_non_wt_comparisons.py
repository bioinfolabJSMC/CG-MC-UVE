"""Read saved results and document non-WT comparisons without refitting models."""
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'results'
METHODS = ['PLS', 'UVE', 'MC-UVE', 'CG-MC-UVE']


def read(name):
    with (RES / name).open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def percent_reduction(reference, candidate):
    return 100.0 * (1.0 - candidate / reference)


def main():
    main_rows = read('model_comparison.csv')
    repeat_rows = read('repeat_metrics.csv')
    saved_summaries = read('repeat_summary.csv')
    stability = read('selection_stability.csv')
    result = {
        'scope': 'Descriptive arithmetic from unchanged saved results; no model fitting, hyperparameter selection, or new statistical tests.',
        'repeat_sd_definition': 'Sample standard deviation (ddof=1) over 30 fixed-hyperparameter Monte Carlo runs.',
        'sd_reduction_definition': '100 * (1 - SD_CG / SD_MC); this is a relative reduction in absolute SD, not the relative SD (SD/mean).',
        'coefficient_of_variation_definition': '100 * sample SD / mean; reported separately from the SD-reduction percentage.',
        'interpretation': 'Lower dispersion of error estimates does not imply lower average error, more stable feature identities, or statistical significance.',
        'datasets': {},
    }
    for dataset in ['corn', 'tablet']:
        rows = {r['method']: r for r in main_rows if r['dataset'] == dataset and r['method'] in METHODS}
        models = {method: {
            'preprocessing': row['preprocessing'],
            'selected_inputs': int(row['n_variables']),
            'latent_variables': int(row['LV']),
            'conditional_nested_RMSECV': float(row['RMSECV']),
            'RMSEP': float(row['RMSEP']),
        } for method, row in rows.items()}
        repeats = {}
        for method in ['MC-UVE', 'CG-MC-UVE']:
            runs = [r for r in repeat_rows if r['dataset'] == dataset and r['method'] == method]
            assert len(runs) == 30 and len({r['run'] for r in runs}) == 30
            saved = next(r for r in saved_summaries if r['dataset'] == dataset and r['method'] == method)
            repeats[method] = {'runs': len(runs)}
            for metric in ['conditional_RMSECV', 'RMSEP']:
                values = [float(r[metric]) for r in runs]
                average, sd = mean(values), stdev(values)
                assert math.isclose(average, float(saved[metric + '_mean']), rel_tol=1e-12, abs_tol=1e-14)
                assert math.isclose(sd, float(saved[metric + '_sd']), rel_tol=1e-12, abs_tol=1e-14)
                repeats[method][metric] = {'mean': average, 'sample_SD': sd,
                                         'coefficient_of_variation_percent': 100.0 * sd / average}
        mc, cg = models['MC-UVE'], models['CG-MC-UVE']
        comparison = {
            'input_count_reduction_percent': percent_reduction(mc['selected_inputs'], cg['selected_inputs']),
            'LV_count_reduction_percent': percent_reduction(mc['latent_variables'], cg['latent_variables']),
            'main_RMSECV_reduction_percent': percent_reduction(mc['conditional_nested_RMSECV'], cg['conditional_nested_RMSECV']),
            'main_RMSEP_reduction_percent': percent_reduction(mc['RMSEP'], cg['RMSEP']),
        }
        for metric in ['conditional_RMSECV', 'RMSEP']:
            comparison[metric + '_SD_reduction_percent'] = percent_reduction(
                repeats['MC-UVE'][metric]['sample_SD'], repeats['CG-MC-UVE'][metric]['sample_SD'])
            comparison[metric + '_repeat_mean_reduction_percent'] = percent_reduction(
                repeats['MC-UVE'][metric]['mean'], repeats['CG-MC-UVE'][metric]['mean'])
        agreement = {r['method']: float(r['chance_corrected_agreement']) for r in stability
                     if r['dataset'] == dataset and r['method'] in ['MC-UVE', 'CG-MC-UVE']}
        result['datasets'][dataset] = {
            'response_unit': '%' if dataset == 'corn' else 'mg',
            'main_models': models,
            'fixed_setting_repeats': repeats,
            'CG_relative_to_MC': comparison,
            'chance_corrected_feature_agreement': agreement,
        }
    (RES / 'non_wt_reporting_audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
