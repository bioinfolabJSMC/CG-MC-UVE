REPRODUCIBLE NUMERICAL ANALYSIS

REVISION 05: EDITORIAL UPDATE ONLY
The main manuscript now focuses on PLS, UVE, MC-UVE, and CG-MC-UVE in the selected
preprocessed spectral representation. The additional WT models and their detailed
results are retained in the Supplementary material. No model, preprocessing,
partition, prediction, or Monte Carlo calculation was rerun for this revision.
All 101 computational result files are preserved byte-for-byte from revision_04.

To verify the delivered result files without recomputation:
python code/verify_results_preservation.py

The portable baseline in results/results_preservation_baseline.json stores file
sizes and SHA-256 hashes. The verifier requires no prior revision folder and
reports missing, changed, or unexpected computational files. Only presentation
audits and the newly added preservation/reporting audit metadata are excluded.
The supplied baseline is a fixed record and must not be silently overwritten.

To reproduce the descriptive non-WT reporting calculations from saved results:
python code/report_non_wt_comparisons.py

This script verifies the 30-run mean and sample SD against repeat_summary.csv and
writes only results/non_wt_reporting_audit.json. It performs no model fitting or
statistical testing. The relative reduction in SD is 100*(1-SD_CG/SD_MC); this is
different from the relative SD, 100*SD/mean, which is recorded separately. Lower
run-to-run error dispersion does not establish better average accuracy, stronger
feature-identity agreement, or statistical significance.

The original analysis remains fully available, including the optional WT branch.
The recomputation commands below deliberately regenerate results and should be
used in a separate copy of the package when preserving the delivered byte-level
baseline is required. Recomputed NPZ serialization or elapsed-time fields need
not be byte-identical even when the numerical calculations agree.

Install the Python packages listed in requirements-analysis.txt. Run commands
from any working directory; inputs and results are resolved relative to this file.

python code/analysis.py --stage all
python code/analysis.py --stage ablations
python code/verify_analysis.py
python code/summarize_results.py

The first command recomputes the data audit, preprocessing comparisons, four main
spectral-variable models, two supplementary WT models, and 30 stochastic repetitions.
The second adds two algorithm ablations in
ablation_comparison.csv. The final two commands independently verify predictions
and regenerate selected-feature and 30-run summary tables.
Use --resume only to deliberately reuse existing main model files. No parallel
execution against the same results directory is supported.

INPUTS
../data/data1_corn.mat and ../data/data2_nir_shootout_2002.mat are unchanged copies
of the user-supplied files. The corn target is propvals.data[:,1] (Oil) and spectra
are m5spec.data (M5 instrument). Tablet spectra and targets are concatenated in the order
calibrate, validate, test; instrument 1, Y[:,2], first 597 spectral columns are used.
Both datasets are stably sorted by target and every fourth sample is assigned to
prediction. The remaining samples form calibration. The exact audit manifests
are saved in results/*_split.csv with one-based source row and original group.

VALIDATION AND ORDER OF OPERATIONS
Stage 1 compares Raw, MSC, SNV, CWT, and D1 using full-spectrum PLS. Five outer
shuffled calibration folds (seed 20261021) evaluate each fixed representation;
four-fold inner CV selects PLS LV by the one-standard-error rule. Pooling the
outer predictions produces the RMSECV in preprocessing_comparison.csv (Table 2).
For each dataset, the representation with the smallest TABLE 2 RMSECV is selected.
This is the first derivative (D1) for M5 corn and CWT for tablets. The separately saved tuning_RMSECV
column is not used to rank the preprocessing methods.

Stage 2 holds that selected representation fixed for all selectors and ablations.
Every wavelength-domain selector receives the preprocessed spectral matrix. The
WT selectors receive the db4 DWT coefficients of that same preprocessed matrix.
Five outer folds evaluate downstream selector/LV tuning, with four-fold inner CV
to choose subset parameters and final PLS LV. Variable rankings are recalculated
inside training folds. Learned preprocessing quantities are fitted on training
spectra only and reused for validation/prediction spectra. The prediction set is
not used to choose preprocessing, subset parameters, or latent variables.

The Stage 2 RMSECV is conditional on the Stage 1 preprocessing choice. Because
the representation was selected using the full calibration set, these errors do
not independently evaluate the entire two-stage procedure; they may be optimistic
with respect to preprocessing selection. The fixed prediction set provides the
held-out evaluation after all choices are locked. The downstream full-spectrum
PLS RMSECV agrees with the selected Table 2 row apart from numerical rounding.

Full-calibration inner-CV RMSECV (tuning_RMSECV) is intentionally saved separately
from the nested outer-CV RMSECV. Do not substitute one for the other.

Monte Carlo coefficient ensembles use 100 random half-sample models with 5 fixed
PLS latent variables. Spectra are mean-centered in each model without autoscaling.
For all methods, the one-standard-error rule is applied to candidate mean squared
validation errors: retain models within min(MSE)+SE at the minimum, then select
the smallest mean variable count, then smallest LV, then smallest MSE.

The 30-run audit freezes preprocessing and hyperparameters at the full-calibration
run-zero choice and varies only Monte Carlo random seeds. For every repeated CV
fit, the selector is recalculated inside its training fold. These conditional CV
values describe algorithmic variation at fixed settings; they are not replacement
estimates of the nested RMSECV. Error bars are sample SD across these 30 runs.

FEATURES
Raw, MSC, SNV, gaus1 CWT (scale 8, symmetric padding 64), and Savitzky-Golay first
derivative (15-point window, degree 2, 2 nm spacing) are compared. WT models apply
db4 DWT, level 3, periodization, after the common preprocessing. Wavelet coefficient
indices are transformed coordinates, not individual acquired wavelengths.
For corn, a selected non-WT coordinate is a first-derivative channel calculated
from its 15-point Savitzky-Golay neighborhood. For tablets, it is a channel in the CWT-preprocessed
spectrum. Its wavelength label is the channel center; calculating it still uses
neighboring acquired spectral values. selected_features.csv records this meaning
in preprocessing, feature_domain, and coordinate_description. A short selected
input vector therefore does not establish the same number of physically isolated
wavelength measurements or a reduction in acquisition bandwidth.

MC-UVE uses abs(mean coefficient)/sample SD. UVE uses leave-one-out coefficient
stability on spectra augmented with equal numbers of uniform noise variables of
amplitude 1e-11, tuning cutoff multipliers 0.3, 0.5, 0.7, 0.9, 1.0. The new method
uses sign-consistent median/MAD reliability as a feature-specific penalty in a
one-step conditional gain criterion. See reliability() and gain_order() for the
complete implementation. The gain guides a greedy subset path, with PLS refitted
after selection; it is not a global optimality or prediction-accuracy guarantee.

FILES
*_data.npz: X,y,wavelength,cal,pred. Indices are zero-based except in CSV audit files.
*_preprocess.npz: cal_spectra,pred_spectra,prediction,oof,lv_curve.
*_final.npz: conditional nested oof,prediction,cal_prediction,selected,cal_features,pred_features,
             and available classic/robust/weight scores.
*_model.json: final calibration-only choices and choices in every outer fold.
*_curve.csv: conditional tuning RMSECV and post-lock prediction diagnostic curves.
*_repeats.npz: run-by-prediction-sample predictions and feature inclusion frequencies.
*_repeat_curves.csv: fixed-LV-at-each-k CV/prediction curves for each random run.
repeat_metrics.csv: fixed-setting repeat statistics.

MEANINGFUL CHECKS
Each invocation verifies PLS1 predictions against scikit-learn PLSRegression with
scale=False, verifies the exact penalized-gain identity, and checks that a duplicated
feature cannot add conditional rank after its duplicate has been selected.

All errors use original response units. RPD = sample SD of prediction references
divided by RMSEP. Prediction R2 = 1-SSE/SST; no squared-correlation substitution.
No data removal, outlier deletion, resplitting, or post-prediction retuning is used.

DATASET-SPECIFIC RECOMPUTATION
To refresh corn only while preserving all tablet numerical results:
python code/analysis.py --stage all --datasets corn
python code/analysis.py --stage ablations --datasets corn
python code/summarize_results.py --datasets corn
python code/verify_analysis.py
python code/plot_results.py --update-datasets corn
python code/verify_tablet_preservation.py

The --datasets option defaults to both datasets. Per-dataset NPZ, JSON, and CSV
artifacts belonging to an unrequested dataset are not rewritten. Shared CSVs
replace only the requested dataset rows, preserving all other cells verbatim.
The supplied tablet_preservation_baseline.json records the prior tablet artifact
hashes and shared-table rows. Its preservation check is intended for this M5-only
revision; an intentional future tablet recomputation may require a new baseline.

In revision_05, plot_results.py reads stored numerical summaries by default. After
an intentional numerical recomputation, use its explicit --refresh-summaries flag
to regenerate plotting-derived numerical summaries before plotting. Omit that
flag when rebuilding figures from the unchanged editorial package.
