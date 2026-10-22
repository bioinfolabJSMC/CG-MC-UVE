"""Independent checks of data identity, partitions, preprocessing, and PLS predictions."""
import hashlib,json
import numpy as np
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from scipy.io import loadmat
import analysis as a

checks={}
expected={'data1_corn.mat':'E28FD4BE274A54CA57B1F2C67EF5A8BF4981F8314BCC73E4C64836FE658C46B5','data2_nir_shootout_2002.mat':'8FAC7B53A2F6A637403FD0832539972854EFBD5FE9CB6F1D5721F3CF3E3C5E58'}
# Exact input identities, with no assumptions about the user's local directory.
checks['input_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.ROOT/'data').glob('*.mat')}
for filename,digest in expected.items():
    assert checks['input_sha256'][filename]==digest.lower()
checks['partitions']={};checks['prediction_reconstruction']={};checks['sequential_preprocessing']={}
checks['integrity']={};source_tables=[]
corn_source=loadmat(a.ROOT/'data/data1_corn.mat',squeeze_me=True,struct_as_record=False)
corn_arrays=np.load(a.RES/'corn_data.npz')
assert np.array_equal(corn_arrays['X'],np.asarray(corn_source['m5spec'].data,dtype=float))
assert np.array_equal(corn_arrays['y'],np.asarray(corn_source['propvals'].data[:,1],dtype=float))
assert np.array_equal(corn_arrays['wavelength'],np.asarray(corn_source['m5spec'].axisscale[1,0],dtype=float))
checks['corn_instrument_identity']=dict(spectral_field='m5spec.data',target_field='propvals.data[:,1]',exact_matrix_match=True)
for name in ['corn','tablet']:
    d=np.load(a.RES/f'{name}_data.npz');cal=d['cal'];test=d['pred'];X=d['X'];y=d['y']
    assert not set(cal)&set(test)
    assert np.array_equal(np.sort(np.r_[cal,test]),np.arange(len(y)))
    order=np.argsort(y,kind='stable')
    assert np.array_equal(test,order[3::4])
    checks['partitions'][name]=dict(calibration=len(cal),prediction=len(test),disjoint=True,complete=True,stable_fourth_rank=True)
    checks['integrity'][name]=dict(nonfinite_spectra=int(np.count_nonzero(~np.isfinite(X))),nonfinite_target=int(np.count_nonzero(~np.isfinite(y))),exact_duplicate_spectral_rows=len(X)-len(np.unique(X,axis=0)),duplicate_target_values=len(y)-len(np.unique(y)),constant_spectral_columns=int(np.count_nonzero(X.std(0)==0)),prediction_below_calibration_range=int(np.count_nonzero(y[test]<y[cal].min())),prediction_above_calibration_range=int(np.count_nonzero(y[test]>y[cal].max())))
    split=pd.read_csv(a.RES/f'{name}_split.csv')
    source=split.groupby(['source_group','partition']).size().reset_index(name='n');source['dataset']=name;source_tables.append(source)
    # Altering prediction spectra cannot change the fitted MSC calibration matrix.
    aa,_=a.preprocess(X[cal],X[test],'MSC');bb,_=a.preprocess(X[cal],X[test]*1.1+.1,'MSC')
    assert np.array_equal(aa,bb)
    table=pd.read_csv(a.RES/'model_comparison.csv')
    if (a.RES/'ablation_comparison.csv').exists():
        table=pd.concat([table,pd.read_csv(a.RES/'ablation_comparison.csv')],ignore_index=True)
    pretable=pd.read_csv(a.RES/'preprocessing_comparison.csv')
    pretable=pretable[pretable.dataset==name]
    minimum=pretable.loc[pretable.RMSECV.idxmin()]
    chosen=json.loads((a.RES/f'{name}_preprocessing_choice.json').read_text())
    assert chosen['best']==minimum.preprocessing
    assert (table.loc[table.dataset==name,'preprocessing']==chosen['best']).all()
    checks['sequential_preprocessing'][name]=dict(selected=chosen['best'],minimum_Table2_RMSECV=float(minimum.RMSECV),all_methods_use_selected_representation=True)
    for _,row in table[table.dataset==name].iterrows():
        method=row['method'];key=method.replace('-','_')
        path=a.RES/f'{name}_{key}_final.npz'
        if not path.exists():continue
        r=np.load(path);idx=r['selected'];lv=int(row['LV'])
        info=json.loads((a.RES/f'{name}_{key}_model.json').read_text())
        assert all(f['preprocessing']==chosen['best'] for f in info['outer_folds'])
        cal_features,pred_features=a.transform_train_test(X[cal],X[test],chosen['best'],method)
        assert np.array_equal(r['cal_features'],cal_features)
        assert np.array_equal(r['pred_features'],pred_features)
        assert abs(np.sqrt(np.mean((r['oof']-y[cal])**2))-row['RMSECV'])<1e-10
        ref=PLSRegression(n_components=lv,scale=False,max_iter=1000,tol=1e-10).fit(r['cal_features'][:,idx],y[cal]).predict(r['pred_features'][:,idx]).ravel()
        difference=float(np.max(np.abs(ref-r['prediction'])))
        assert difference<1e-6,(name,method,difference)
        rmsep=float(np.sqrt(np.mean((r['prediction']-y[test])**2)))
        assert abs(rmsep-row['RMSEP'])<1e-10
        assert np.isfinite(r['oof']).all() and len(r['oof'])==len(cal)
        checks['prediction_reconstruction'][f'{name}_{method}']=dict(max_abs_difference_sklearn=difference,RMSEP_matches_csv=True,finite_outer_oof=True)
    pls=table[(table.dataset==name)&(table.method=='PLS')].iloc[0]
    assert abs(pls.RMSECV-minimum.RMSECV)<1e-10
    checks['sequential_preprocessing'][name]['PLS_RMSECV_matches_selected_Table2_row']=True
checks['MSC_training_reference_isolated']=True
repeat_files=list(a.RES.glob('*_repeats.npz'))
if len(repeat_files)==8:
    metrics=pd.read_csv(a.RES/'repeat_metrics.csv')
    assert len(metrics)==240
    assert (metrics.groupby(['dataset','method']).size()==30).all()
    for name in ['corn','tablet']:
        d=np.load(a.RES/f'{name}_data.npz');truth=d['y'][d['pred']]
        for method in ['MC-UVE','CG-MC-UVE','WT-MC-UVE','WT-CG-MC-UVE']:
            key=method.replace('-','_');r=np.load(a.RES/f'{name}_{key}_repeats.npz');f=np.load(a.RES/f'{name}_{key}_final.npz')
            assert r['predictions'].shape==(30,len(truth))
            assert np.max(np.abs(r['predictions'][0]-f['prediction']))<1e-10
            assert abs(r['inclusion_frequency'].sum()-len(f['selected']))<1e-10
            observed=np.sqrt(np.mean((r['predictions']-truth[None,:])**2,axis=1))
            saved=metrics[(metrics.dataset==name)&(metrics.method==method)].sort_values('run')['RMSEP'].values
            assert np.max(np.abs(observed-saved))<1e-10
    checks['stochastic_audit']=dict(dataset_method_groups=8,runs_per_group=30,total_runs=240,run_zero_matches_primary=True,all_RMSEP_reconstructed=True,inclusion_counts_match=True)
else:
    checks['stochastic_audit']=dict(completed_groups=len(repeat_files),status='incomplete')
pd.concat(source_tables,ignore_index=True).to_csv(a.RES/'original_group_partition_summary.csv',index=False)
a.dump(checks,a.RES/'independent_verification.json')
print(json.dumps(checks,indent=2))
