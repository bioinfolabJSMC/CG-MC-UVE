"""Publication figures from the supplied spectra and saved numerical results.

Run from any directory with the requirements in this package installed.
All raster exports are 300 dpi at their saved physical size; vector PDF and SVG
retain text and paths. Figure text uses Times New Roman, as in the reference.
By default, plotting reads the saved numerical results without modifying them.
Use --refresh-summaries only when explicitly regenerating derived CSV summaries.
"""
from pathlib import Path
import json,csv,argparse
import numpy as np
import pandas as pd
from scipy.io import loadmat
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import AutoMinorLocator, MaxNLocator
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'figures'
FIG.mkdir(exist_ok=True)
for fp in ['C:/Windows/Fonts/times.ttf','C:/Windows/Fonts/timesbd.ttf','C:/Windows/Fonts/timesi.ttf']:
    if Path(fp).exists(): font_manager.fontManager.addfont(fp)
try:
    font_manager.findfont(font_manager.FontProperties(family='Times New Roman'),fallback_to_default=False)
except ValueError as exc:
    raise RuntimeError('Install Times New Roman before generating the publication figures.') from exc
plt.rcParams.update({'font.family':'Times New Roman','font.size':14,
 'axes.labelsize':15,'axes.titlesize':15,'xtick.labelsize':13,'ytick.labelsize':13,
 'legend.fontsize':12,'axes.linewidth':0.8,'lines.linewidth':1.2,
 'xtick.direction':'in','ytick.direction':'in','xtick.top':True,'ytick.right':True,
 'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white',
 'mathtext.fontset':'custom','mathtext.rm':'Times New Roman','mathtext.it':'Times New Roman:italic',
 'mathtext.bf':'Times New Roman:bold'})
COLORS = ['#000000','#2255CC','#DD3333','#159447','#AA55AA','#E09020','#559AAA']
DATASET_NAMES=['Corn (m5)','Tablets']

def merge_dataset_rows(frame,path,update_datasets):
    """Update selected data sets while retaining other saved CSV strings."""
    path=Path(path)
    if path.exists():
        with path.open(newline='',encoding='utf-8') as stream:
            reader=csv.DictReader(stream);fields=reader.fieldnames
            saved=[r for r in reader if r['dataset'] not in update_datasets]
        fresh=frame[frame.dataset.isin(update_datasets)].to_dict('records')
    else:
        fields=list(frame.columns);saved=[];fresh=frame.to_dict('records')
    rows=fresh+saved;rows.sort(key=lambda r:{'corn':0,'tablet':1}[r['dataset']])
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def savefig(fig, name):
    kwargs={'dpi':300,'bbox_inches':'tight','pad_inches':0.08}
    fig.savefig(FIG/f'{name}.png',**kwargs)
    # A shared raster prevents layout recalculation between PNG and TIFF exports.
    with Image.open(FIG/f'{name}.png') as raster:
        raster.convert('RGB').save(FIG/f'{name}.tiff',compression='tiff_lzw',dpi=(300,300))
    for ext in ['pdf','svg']:
        fig.savefig(FIG/f'{name}.{ext}',**kwargs)
    plt.close(fig)

def style(ax, letter=None):
    ax.tick_params(which='both',direction='in',top=True,right=True)
    if ax.get_xscale()=='linear': ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    if ax.get_yscale()=='linear': ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    if letter: ax.text(0.0,1.02,f'({letter})',transform=ax.transAxes,ha='left',va='bottom',fontsize=16)

def raw_data():
    c=loadmat(ROOT/'data/data1_corn.mat',simplify_cells=True)
    t=loadmat(ROOT/'data/data2_nir_shootout_2002.mat',simplify_cells=True)
    items=[(DATASET_NAMES[0],np.asarray(c['m5spec']['data'],float),np.asarray(c['propvals']['data'],float)[:,1],np.arange(1100,2500,2),'Oil content (%)'),
           ('Tablets',np.vstack([t[f'{g}_1'] for g in ['calibrate','validate','test']])[:,:597].astype(float),np.concatenate([t[f'{g}_Y'][:,2] for g in ['calibrate','validate','test']]).astype(float),np.arange(600,1794,2),'API content (mg)')]
    ds=[]
    for name,X,y,w,label in items:
        order=np.argsort(y,kind='stable'); test=order[3::4]
        train=order[np.arange(len(y))%4!=3]
        ds.append(dict(name=name,X=X,y=y,w=w,label=label,train=train,test=test,order=order))
    return ds

def descriptive_figures():
    ds=raw_data()
    fig,axes=plt.subplots(1,2,figsize=(10.2,3.65),layout='constrained')
    for i,(ax,d) in enumerate(zip(axes,ds)):
        for row in d['X']: ax.plot(d['w'],row,color='#4477AA',alpha=.16,lw=.45)
        ax.plot(d['w'],d['X'].mean(axis=0),color='black',lw=1.35,label='Mean spectrum')
        ax.set(xlabel='Wavelength (nm)',ylabel='Absorbance (a.u.)',title=f"{d['name']}  (n = {len(d['y'])})")
        ax.legend(frameon=False,loc='best');style(ax,'AB'[i])
    savefig(fig,'Figure_1_raw_spectra')
    fig,axes=plt.subplots(2,2,figsize=(9.4,6.5),layout='constrained')
    for i,d in enumerate(ds):
        rank=np.empty(len(d['y']),int);rank[d['order']]=np.arange(1,len(d['y'])+1)
        for ids,color,label in [(d['train'],'#2255CC','Calibration'),(d['test'],'#DD3333','Prediction')]:
            axes[0,i].scatter(rank[ids],d['y'][ids],s=13,color=color,alpha=.75,label=f'{label} (n = {len(ids)})')
            axes[1,i].hist(d['y'][ids],bins=14,density=True,histtype='step',lw=1.5,color=color,label=label)
        axes[0,i].set(xlabel='Rank after stable target sorting',ylabel=d['label'],title=d['name'])
        axes[1,i].set(xlabel=d['label'],ylabel='Probability density')
        axes[0,i].legend(frameon=False);axes[1,i].legend(frameon=False)
        style(axes[0,i],'AB'[i]);style(axes[1,i],'CD'[i])
    savefig(fig,'Figure_S1_partition_audit')
    return ds

RES=ROOT/'results'
METHODS=['PLS','UVE','MC-UVE','CG-MC-UVE','WT-MC-UVE','WT-CG-MC-UVE']
SHORT=['PLS','UVE','MC-UVE','CG-MC-UVE','WT-MC-UVE','WT-CG-MC-UVE']

def namekey(method): return method.replace('-','_')
def prepname(p): return {'Raw':'Raw','MSC':'MSC','SNV':'SNV','CWT':'CWT','D1':'First derivative'}[p]
def chosen_prep(key): return json.loads((RES/f'{key}_preprocessing_choice.json').read_text())['best']

def spectral_ylabel(prep):
    return {'Raw':'Absorbance (a.u.)','MSC':'MSC response','SNV':'SNV response','CWT':'CWT response','D1':'First derivative (nm$^{-1}$)'}[prep]

def preprocessing_figures():
    if not (RES/'preprocessing_comparison.csv').exists(): return
    ds=raw_data()
    fig,axes=plt.subplots(2,2,figsize=(10,6.9),layout='constrained')
    for i,(key,d) in enumerate(zip(['corn','tablet'],ds)):
        prep=chosen_prep(key);a=np.load(RES/f'{key}_{prep}_preprocess.npz')
        for row in a['cal_spectra']:axes[0,i].plot(d['w'],row,color='#2255CC',alpha=.2,lw=.4)
        axes[0,i].plot(d['w'],a['cal_spectra'].mean(0),color='black',lw=1.2)
        axes[0,i].set(title=f"{d['name']}: {prepname(prep)}",xlabel='Wavelength (nm)',ylabel=spectral_ylabel(prep))
        comparison=pd.read_csv(RES/'preprocessing_comparison.csv')
        c=comparison[comparison.dataset==key].set_index('preprocessing').loc[['Raw','MSC','SNV','CWT','D1']]
        colors=['#DD3333' if pp==prep else '#B9C9DE' for pp in c.index]
        axes[1,i].bar(np.arange(5),c.RMSECV,color=colors,width=.62)
        axes[1,i].set(xticks=np.arange(5),xticklabels=['Raw','MSC','SNV','CWT','First\nderivative'],
            ylabel='RMSECV (%)' if key=='corn' else 'RMSECV (mg)',xlabel='Preprocessing method')
        bestpos=list(c.index).index(prep)
        axes[1,i].text(bestpos,float(c.loc[prep,'RMSECV'])+.025*float(c.RMSECV.max()),
            'Selected',ha='center',va='bottom',fontsize=11,color='#AA2020')
        axes[1,i].set_ylim(0,float(c.RMSECV.max())*1.17)
        style(axes[0,i],'AB'[i]);style(axes[1,i],'CD'[i])
    savefig(fig,'Figure_2_preprocessing_and_PLS')
    fig,axes=plt.subplots(5,2,figsize=(10,12),layout='constrained')
    for i,(key,d) in enumerate(zip(['corn','tablet'],ds)):
        for j,p in enumerate(['Raw','MSC','SNV','CWT','D1']):
            a=np.load(RES/f'{key}_{p}_preprocess.npz')['cal_spectra']
            for row in a:axes[j,i].plot(d['w'],row,color='#2255CC',alpha=.13,lw=.35)
            axes[j,i].plot(d['w'],a.mean(0),color='black',lw=.9)
            axes[j,i].set(title=f"{d['name']}: {prepname(p)}",xlabel='Wavelength (nm)',ylabel=spectral_ylabel(p))
            style(axes[j,i],chr(65+j*2+i))
    savefig(fig,'Figure_S2_all_preprocessing')

def model_figures():
    if not (RES/'model_comparison.csv').exists(): return
    tab=pd.read_csv(RES/'model_comparison.csv');ds=raw_data()
    if any(not (RES/f'{d}_{namekey(m)}_final.npz').exists() for d in ['corn','tablet'] for m in METHODS):return
    for field,fn,label in [('RMSEP','Figure_3_prediction_error_paths','Prediction RMSE'),('RMSECV','Figure_S3_calibration_error_paths','Calibration tuning RMSECV')]:
        fig,axes=plt.subplots(1,2,figsize=(10,3.8),layout='constrained')
        for i,(key,d) in enumerate(zip(['corn','tablet'],ds)):
            for j,m in enumerate(['MC-UVE','CG-MC-UVE']):
                a=pd.read_csv(RES/f'{key}_{namekey(m)}_curve.csv')
                info=json.loads((RES/f'{key}_{namekey(m)}_model.json').read_text())
                if m=='CG-MC-UVE': a=a[a['key'].astype(str).str.startswith(info['choice']['key'].split(':')[0]+':')]
                a=a.sort_values('n_variables')
                axes[i].plot(a.n_variables,a[field],'-o',ms=3,color=COLORS[j+1],label=m)
                row=tab[(tab.dataset==key)&(tab.method==m)].iloc[0]
                axes[i].axvline(row.n_variables,color=COLORS[j+1],ls=':',lw=.8)
            axes[i].set(title=d['name'],xlabel='Number of selected spectral variables',ylabel=label+(' (%)' if key=='corn' else ' (mg)'),xscale='log')
            axes[i].legend(frameon=False);style(axes[i],'AB'[i])
        savefig(fig,fn)
    fig,axes=plt.subplots(2,2,figsize=(10,6.8),layout='constrained')
    for i,(key,d) in enumerate(zip(['corn','tablet'],ds)):
        prep=chosen_prep(key)
        mean=np.load(RES/f'{key}_{prep}_preprocess.npz')['cal_spectra'].mean(0)
        axes[0,i].plot(d['w'],mean,color='black',lw=1)
        for j,m in enumerate(['MC-UVE','CG-MC-UVE']):
            f=np.load(RES/f'{key}_{namekey(m)}_final.npz');ix=f['selected']
            axes[0,i].scatter(d['w'][ix],mean[ix],s=19 if j else 9,facecolors='none',edgecolors=COLORS[j+1],marker='o' if j else 's',label=f'{m} ({len(ix)})')
            rp=RES/f'{key}_{namekey(m)}_repeats.npz'
            if rp.exists(): axes[1,i].plot(d['w'],np.load(rp)['inclusion_frequency'],color=COLORS[j+1],lw=.8,label=m)
        axes[0,i].set(title=f"{d['name']}: {prepname(prep)}",xlabel='Channel position (nm)',ylabel='Mean '+('absorbance (a.u.)' if prep=='Raw' else spectral_ylabel(prep)));axes[0,i].legend(frameon=False)
        axes[1,i].set(xlabel='Channel position (nm)',ylabel='Selection frequency',ylim=(-.03,1.08));axes[1,i].legend(frameon=False)
        style(axes[0,i],'AB'[i]);style(axes[1,i],'CD'[i])
    savefig(fig,'Figure_4_selected_channels')
    fig,axes=plt.subplots(2,2,figsize=(9,7),layout='constrained')
    for i,(key,d) in enumerate(zip(['corn','tablet'],ds)):
        for j,m in enumerate(['MC-UVE','CG-MC-UVE']):
            f=np.load(RES/f'{key}_{namekey(m)}_final.npz');X=f['cal_features'][:,f['selected']]
            cc=np.corrcoef(X,rowvar=False)
            k=cc.shape[0]
            im=axes[i,j].imshow(cc,vmin=-1,vmax=1,cmap='coolwarm',aspect='auto',interpolation='none',extent=(.5,k+.5,k+.5,.5))
            if k<=8:
                axes[i,j].set(xticks=np.arange(1,k+1),yticks=np.arange(1,k+1))
            else:
                axes[i,j].xaxis.set_major_locator(MaxNLocator(nbins=5,integer=True))
                axes[i,j].yaxis.set_major_locator(MaxNLocator(nbins=5,integer=True))
            axes[i,j].set(title=f"{d['name']}: {m}",xlabel='Selected feature rank',ylabel='Selected feature rank')
            axes[i,j].text(.02,.98,f'({chr(65+i*2+j)})',transform=axes[i,j].transAxes,va='top')
    fig.colorbar(im,ax=axes,label='Pearson correlation',shrink=.8)
    savefig(fig,'Figure_S4_selected_feature_correlations')
    fig,axes=plt.subplots(2,2,figsize=(10,6.8),layout='constrained')
    for i,(key,d) in enumerate(zip(['corn','tablet'],ds)):
        f=np.load(RES/f'{key}_WT_CG_MC_UVE_final.npz');A=f['cal_features'];ix=f['selected']
        axes[0,i].plot(np.arange(1,A.shape[1]+1),A.mean(0),color='black',lw=.8)
        axes[0,i].scatter(ix+1,A.mean(0)[ix],color='#DD3333',s=20,label=f'Selected ({len(ix)})')
        axes[0,i].set(title=d['name'],xlabel='DWT coefficient index',ylabel='Mean coefficient');axes[0,i].legend(frameon=False)
        pth=RES/f'{key}_WT_CG_MC_UVE_repeats.npz'
        if pth.exists():axes[1,i].stem(np.arange(1,A.shape[1]+1),np.load(pth)['inclusion_frequency'],linefmt='r-',markerfmt=' ',basefmt='k-')
        axes[1,i].set(xlabel='DWT coefficient index',ylabel='Selection frequency',ylim=(-.02,1.05))
        style(axes[0,i],'AB'[i]);style(axes[1,i],'CD'[i])
    savefig(fig,'Figure_S5_wavelet_features')

def repeated_figures(update_datasets=('corn','tablet'),refresh_summaries=False):
    files=[RES/f'{d}_WT_CG_MC_UVE_repeat_curves.csv' for d in ['corn','tablet']]
    if not all(p.exists() for p in files):return
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    tables=[]
    for i,(key,pth) in enumerate(zip(['corn','tablet'],files)):
        a=pd.read_csv(pth);g=a.groupby('n_variables').agg(mean_RMSECV=('RMSECV','mean'),SD_RMSECV=('RMSECV','std'),mean_RMSEP=('RMSEP','mean'),SD_RMSEP=('RMSEP','std'),runs=('run','nunique')).reset_index()
        axes[i].errorbar(g.n_variables,g.mean_RMSECV,yerr=g.SD_RMSECV,fmt='o-',color='#DD3333',ms=4,capsize=3,label='WT-CG-MC-UVE')
        mc=pd.read_csv(RES/f'{key}_WT_MC_UVE_repeat_curves.csv');h=mc.groupby('n_variables').RMSECV.agg(['mean','std']).reset_index()
        axes[i].errorbar(h.n_variables,h['mean'],yerr=h['std'],fmt='s-',color='#2255CC',ms=3,capsize=2,label='WT-MC-UVE')
        axes[i].set(title=DATASET_NAMES[i],xlabel='Number of wavelet coefficients',ylabel='Conditional RMSECV'+(' (%)' if key=='corn' else ' (mg)'),xscale='log');axes[i].legend(frameon=False);style(axes[i],'AB'[i])
        g.insert(0,'dataset',key);tables.append(g)
    savefig(fig,'Figure_S7_wavelet_repeated_CV')
    if refresh_summaries:
        merge_dataset_rows(pd.concat(tables,ignore_index=True),RES/'wavelet_count_summary.csv',update_datasets)
    rm=pd.read_csv(RES/'repeat_metrics.csv')
    fig,axes=plt.subplots(2,2,figsize=(10,7),layout='constrained')
    ms=METHODS[2:]
    for j,key in enumerate(['corn','tablet']):
        for i,col in enumerate(['conditional_RMSECV','RMSEP']):
            v=[rm[(rm.dataset==key)&(rm.method==m)][col].to_numpy() for m in ms]
            axes[i,j].boxplot(v,tick_labels=['MC','CG','WT-MC','WT-CG'],patch_artist=True,boxprops={'facecolor':'#DDE7F6'},medianprops={'color':'#DD3333'},showfliers=True)
            axes[i,j].set(ylabel=('Conditional RMSECV' if i==0 else 'Prediction RMSE')+(' (%)' if key=='corn' else ' (mg)'),title=DATASET_NAMES[j] if i==0 else '')
            style(axes[i,j],chr(65+i*2+j))
    savefig(fig,'Figure_S6_stochastic_variation')

def bootstrap_comparison(update_datasets=('corn','tablet')):
    if not all((RES/f'{d}_CG_MC_UVE_final.npz').exists() for d in ['corn','tablet']):return
    rng=np.random.default_rng(82931);out=[];target=RES/'paired_bootstrap.csv'
    for key,d in zip(['corn','tablet'],raw_data()):
        y=d['y'][d['test']];ix=rng.integers(len(y),size=(5000,len(y)))
        if target.exists() and key not in update_datasets:continue
        base=np.load(RES/f'{key}_MC_UVE_final.npz')['prediction']
        for method in ['CG-MC-UVE','WT-CG-MC-UVE']:
            pr=np.load(RES/f'{key}_{namekey(method)}_final.npz')['prediction']
            diff=np.sqrt(np.mean((pr[ix]-y[ix])**2,1))-np.sqrt(np.mean((base[ix]-y[ix])**2,1))
            out.append(dict(dataset=key,method=method,comparator='MC-UVE',delta_RMSEP=np.sqrt(np.mean((pr-y)**2))-np.sqrt(np.mean((base-y)**2)),CI_low=np.quantile(diff,.025),CI_high=np.quantile(diff,.975),bootstrap_resamples=5000))
    merge_dataset_rows(pd.DataFrame(out),target,update_datasets)

def workflow_and_graphical_abstracts():
    if not all((RES/f'{d}_CG_MC_UVE_final.npz').exists() for d in ['corn','tablet']):return
    from matplotlib.patches import FancyBboxPatch
    tab=pd.read_csv(RES/'model_comparison.csv');ds=raw_data()
    repeat=pd.read_csv(RES/'repeat_summary.csv')
    preps={key:chosen_prep(key) for key in ['corn','tablet']}
    def box(ax,x,y,w,h,text,color='#E6EDF6',size=12):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.01,rounding_size=0.012',facecolor=color,edgecolor='#304A70',lw=1))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size)
    def arrow(ax,a,b):ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','lw':1.3,'color':'#304A70'})
    fig,ax=plt.subplots(figsize=(10.6,6.1));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    box(ax,.02,.76,.27,.19,'Target-ordered partition\nCorn (m5): 60 / 20\nTablets: 492 / 163')
    box(ax,.365,.76,.27,.19,'Compare preprocessing\nPLS calibration validation\nLowest Table 2 RMSECV')
    box(ax,.71,.76,.27,.19,f'Fix spectral representation\nCorn: {prepname(preps["corn"])}\nTablets: {prepname(preps["tablet"])}',color='#E8F1E5')
    arrow(ax,(.29,.855),(.365,.855));arrow(ax,(.635,.855),(.71,.855))
    box(ax,.71,.425,.27,.21,'Preprocessed spectra\nWavelength-indexed\nspectral channels',color='#E8F1E5')
    box(ax,.365,.425,.27,.21,'Variable selection\nUVE / MC-UVE / CG-MC-UVE\nTraining-fold estimation')
    box(ax,.02,.425,.27,.21,'PLS calibration\nSubset and LV tuning\nOne-standard-error rule')
    arrow(ax,(.845,.76),(.845,.635));arrow(ax,(.71,.53),(.635,.53));arrow(ax,(.365,.53),(.29,.53))
    box(ax,.02,.09,.27,.21,'Model evaluation\nRMSECV conditional on\nselected preprocessing')
    box(ax,.365,.09,.27,.21,'Locked prediction set\nRMSEP in target units\nNo prediction-set tuning')
    box(ax,.71,.09,.27,.21,'Sampling variability\n30 independent ensembles\nFixed hyperparameters')
    arrow(ax,(.155,.425),(.155,.30));arrow(ax,(.29,.195),(.365,.195));arrow(ax,(.635,.195),(.71,.195))
    savefig(fig,'Figure_5_analysis_workflow')
    # Alternative 1: actual selected representations, sequential method, and dimensions.
    fig=plt.figure(figsize=(10.8,5.7));gs=fig.add_gridspec(2,3,width_ratios=[1.1,1.2,1.1],wspace=.45,hspace=1.05)
    for i,(key,d) in enumerate(zip(['corn','tablet'],ds)):
        prep=preps[key];mean=np.load(RES/f'{key}_{prep}_preprocess.npz')['cal_spectra'].mean(0)
        a=fig.add_subplot(gs[i,0]);a.plot(d['w'],mean,color=COLORS[i+1])
        a.set(title=f'{d["name"]}\n{prepname(prep)}',xlabel='Channel position (nm)',ylabel=spectral_ylabel(prep));style(a)
    a=fig.add_subplot(gs[:,1]);a.set(xlim=(0,1),ylim=(0,1));a.axis('off')
    box(a,.05,.77,.9,.19,'Minimum preprocessing\nRMSECV\nFix spectral representation',size=11)
    box(a,.05,.52,.9,.17,'Monte Carlo PLS\nCoefficient reliability',size=12)
    box(a,.05,.27,.9,.17,'Conditional penalized gain\nSelect spectral variables',color='#E8F1E5',size=12)
    box(a,.05,.02,.9,.17,'Selected inputs\nPLS recalibration',size=12)
    arrow(a,(.5,.77),(.5,.69));arrow(a,(.5,.52),(.5,.44));arrow(a,(.5,.27),(.5,.19))
    for i,key in enumerate(['corn','tablet']):
        a=fig.add_subplot(gs[i,2]);rr=tab[(tab.dataset==key)&tab.method.isin(['MC-UVE','CG-MC-UVE'])].set_index('method')
        vals=[rr.loc[m,'n_variables'] for m in ['MC-UVE','CG-MC-UVE']]
        a.bar(['MC-UVE','CG-MC-UVE'],vals,color=['#2255CC','#DD3333'],width=.55)
        for j,v in enumerate(vals):a.text(j,v+.03*max(vals),str(int(v)),ha='center')
        a.set(title=DATASET_NAMES[i],ylabel='Selected spectral variables',ylim=(0,max(vals)*1.3));style(a)
    fig.suptitle('Preprocessing selection precedes variable selection',fontsize=16,y=1.02)
    fig.text(.5,-.04,'CG-MC-UVE: errors decrease for tablets and increase for corn relative to MC-UVE.',
        ha='center',fontsize=12)
    savefig(fig,'Graphical_abstract_1')
    # Alternative 2: input count, latent variables, and error ratios for spectral selection.
    fig,axes=plt.subplots(1,2,figsize=(10.3,4.6),layout='constrained')
    ratios={}
    for key in ['corn','tablet']:
        group=tab[tab.dataset==key].set_index('method')
        base=group.loc['MC-UVE'];cg=group.loc['CG-MC-UVE']
        ratios[key]=[cg.n_variables/base.n_variables,cg.LV/base.LV,cg.RMSECV/base.RMSECV,cg.RMSEP/base.RMSEP]
    ymax=max(1.4,max(max(v) for v in ratios.values())*1.25)
    for i,key in enumerate(['corn','tablet']):
        bars=axes[i].bar(np.arange(4),ratios[key],width=.58,color='#DD3333',label='CG-MC-UVE')
        axes[i].bar_label(bars,labels=[f'{value:.2f}' for value in ratios[key]],padding=4,fontsize=12)
        axes[i].axhline(1,color='black',ls='--',lw=1,label='MC-UVE reference')
        axes[i].set(xticks=np.arange(4),xticklabels=['Inputs','LVs','RMSECV','RMSEP'],ylabel='Ratio to MC-UVE',
            title=f'{DATASET_NAMES[i]}: {prepname(preps[key])}',ylim=(0,ymax))
        axes[i].legend(frameon=False,loc='upper left',fontsize=11);style(axes[i])
    fig.suptitle('Fewer spectral inputs and latent variables',fontsize=16)
    savefig(fig,'Graphical_abstract_2')
    # Alternative 3: model dimension and run-to-run error SD under fixed hyperparameters.
    with plt.rc_context({'axes.labelsize':13,'axes.titlesize':14,'xtick.labelsize':11,'ytick.labelsize':11}):
        fig,axes=plt.subplots(2,3,figsize=(11,6.3),layout='constrained')
        for i,key in enumerate(['corn','tablet']):
            model=tab[tab.dataset==key].set_index('method')
            runs=repeat[repeat.dataset==key].set_index('method')
            methods=['MC-UVE','CG-MC-UVE'];unit='%' if key=='corn' else 'mg'
            metrics=[([model.loc[m,'LV'] for m in methods],'Latent variables',lambda v:f'{int(v)}'),
                ([runs.loc[m,'conditional_RMSECV_sd'] for m in methods],f'RMSECV SD ({unit})',lambda v:f'{v:.4f}'),
                ([runs.loc[m,'RMSEP_sd'] for m in methods],f'RMSEP SD ({unit})',lambda v:f'{v:.4f}')]
            for j,(values,ylabel,formatter) in enumerate(metrics):
                bars=axes[i,j].bar(methods,values,width=.55,color=['#2255CC','#DD3333'])
                axes[i,j].bar_label(bars,labels=[formatter(v) for v in values],padding=3,fontsize=11)
                axes[i,j].set(title=DATASET_NAMES[i],ylabel=ylabel,ylim=(0,max(values)*1.3));style(axes[i,j])
                if j==0:axes[i,j].yaxis.set_major_locator(MaxNLocator(integer=True))
        fig.suptitle('Lower model dimension and lower error variation across 30 runs',fontsize=16)
        fig.supxlabel('Fixed hyperparameters; lower error SD does not imply lower prediction error.',fontsize=12)
        savefig(fig,'Graphical_abstract_3')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--update-datasets',nargs='+',choices=['corn','tablet'],default=['corn','tablet'],
        help='Data sets to update only when --refresh-summaries is supplied; render figures for both.')
    parser.add_argument('--refresh-summaries',action='store_true',
        help='Explicitly regenerate derived CSV summaries. Omit to preserve every saved result file.')
    args=parser.parse_args()
    descriptive_figures();preprocessing_figures();model_figures()
    repeated_figures(args.update_datasets,refresh_summaries=args.refresh_summaries)
    if args.refresh_summaries:bootstrap_comparison(args.update_datasets)
    workflow_and_graphical_abstracts()
