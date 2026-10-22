"""Create machine-readable selected-feature lists and 30-run summary tables."""
import argparse,json
import numpy as np
import pandas as pd
import analysis as a

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--datasets',nargs='+',choices=['corn','tablet'],default=['corn','tablet']);args=parser.parse_args();datasets=args.datasets
    table=pd.read_csv(a.RES/'model_comparison.csv');features=[]
    if (a.RES/'ablation_comparison.csv').exists():
        table=pd.concat([table,pd.read_csv(a.RES/'ablation_comparison.csv')],ignore_index=True)
    table=table[table.dataset.isin(datasets)]
    for _,r in table.iterrows():
        name=r['dataset'];method=r['method'];key=method.replace('-','_')
        z=np.load(a.RES/f'{name}_{key}_final.npz');d=np.load(a.RES/f'{name}_data.npz')
        wm=pd.read_csv(a.RES/f'{name}_wavelet_metadata.csv')
        for rank,j in enumerate(z['selected']):
            wave=method.startswith('WT-')
            score_key='robust' if ('CG-' in method or method=='ROBUST') else 'classic'
            features.append(dict(dataset=name,method=method,preprocessing=r['preprocessing'],feature_domain='DWT coefficients after preprocessing' if wave else 'preprocessed spectral channels',coordinate_description='DWT coefficient index' if wave else ('CWT channel center wavelength' if r['preprocessing']=='CWT' else ('first-derivative channel center wavelength' if r['preprocessing']=='D1' else 'spectral channel wavelength')),selection_order=rank+1,index_0=int(j),index_1=int(j)+1,wavelength_nm=np.nan if wave else d['wavelength'][j],wavelet_band=wm.iloc[j]['band'] if wave else '',wavelet_index_in_band=int(wm.iloc[j]['band_index_1']) if wave else np.nan,score=float(z[score_key][j]) if score_key in z and method!='GAIN' else np.nan,weight=float(z['weight'][j]) if 'weight' in z and ('CG-' in method or method=='GAIN') else np.nan))
    a.merge_dataset_rows(features,a.RES/'selected_features.csv',datasets)
    if (a.RES/'repeat_metrics.csv').exists():
        runs=pd.read_csv(a.RES/'repeat_metrics.csv')
        runs=runs[runs.dataset.isin(datasets)]
        agg=runs.groupby(['dataset','method']).agg(runs=('run','count'),n_variables_mean=('n_variables','mean'),n_variables_sd=('n_variables','std'),conditional_RMSECV_mean=('conditional_RMSECV','mean'),conditional_RMSECV_sd=('conditional_RMSECV','std'),RMSEP_mean=('RMSEP','mean'),RMSEP_sd=('RMSEP','std'),RPD_mean=('RPD','mean'),RPD_sd=('RPD','std')).reset_index()
        a.merge_dataset_rows(agg.to_dict('records'),a.RES/'repeat_summary.csv',datasets)
    rows=[]
    for name in datasets:
        for method in ['WT-MC-UVE','WT-CG-MC-UVE']:
            f=a.RES/f'{name}_{method.replace("-","_")}_repeat_curves.csv'
            if not f.exists():continue
            df=pd.read_csv(f);gg=df.groupby(['key','n_variables','LV']).agg(runs=('run','count'),RMSECV_mean=('RMSECV','mean'),RMSECV_sd=('RMSECV','std'),RMSEP_mean=('RMSEP','mean'),RMSEP_sd=('RMSEP','std')).reset_index()
            gg['dataset']=name;gg['method']=method;rows.append(gg)
    if rows:a.merge_dataset_rows(pd.concat(rows,ignore_index=True).to_dict('records'),a.RES/'wavelet_count_comparison.csv',datasets)
    stability=[]
    for name in datasets:
        for method in ['MC-UVE','CG-MC-UVE','WT-MC-UVE','WT-CG-MC-UVE']:
            f=a.RES/f'{name}_{method.replace("-","_")}_repeats.npz'
            if not f.exists():continue
            z=np.load(f);M=z['predictions'].shape[0];freq=z['inclusion_frequency'];p=len(freq)
            count=np.rint(freq*M);k=float(freq.sum())
            intersection=float(np.sum(count*(count-1))/(M*(M-1)))
            agreement=(intersection-k*k/p)/(k-k*k/p)
            stability.append(dict(dataset=name,method=method,runs=M,feature_space_size=p,k=k,mean_pairwise_intersection=intersection,chance_corrected_agreement=agreement))
    if stability:a.merge_dataset_rows(stability,a.RES/'selection_stability.csv',datasets)
    print('Summary tables saved')

if __name__=='__main__':main()
