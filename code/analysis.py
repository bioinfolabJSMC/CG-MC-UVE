"""Sequential preprocessing comparison and spectral selection benchmark.
Run: python code/analysis.py --stage all
After the fixed target-ordered split, prediction responses are used only for
evaluation, after calibration-only tuning.
Preprocessing is fixed at the minimum Table 2 RMSECV before downstream selection.
Downstream RMSECV nests selector/LV tuning, conditional on that representation.
"""
from __future__ import annotations
import os
for _v in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[_v]='1'
import argparse, csv, json, hashlib, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from scipy.io import loadmat
from scipy.signal import savgol_filter
import pywt
from sklearn.model_selection import KFold
from threadpoolctl import threadpool_limits
threadpool_limits(1)
ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'results'; RES.mkdir(exist_ok=True)
SEED=20261021
PRE=['Raw','MSC','SNV','CWT','D1']
METHODS=['PLS','UVE','MC-UVE','CG-MC-UVE','WT-MC-UVE','WT-CG-MC-UVE']
MAXLV=15; MC_RUNS=100; SELECTOR_LV=5
KGRID=[2,4,6,8,12,16,24,32,48,64,96,128,192,256,384,512]
TAUS=[0.01,0.1,1.0]
UVE_MULT=[0.3,0.5,0.7,0.9,1.0]

def dump(obj,path):
    def cv(v):
        if isinstance(v,np.ndarray): return v.tolist()
        if isinstance(v,np.generic): return v.item()
        raise TypeError(type(v).__name__)
    Path(path).write_text(json.dumps(obj,indent=2,default=cv,allow_nan=False),encoding='utf8')

def merge_dataset_rows(rows,path,datasets):
    """Replace requested dataset rows, preserving all other CSV values verbatim."""
    path=Path(path)
    if path.exists():
        with path.open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames
            old=[r for r in reader if r['dataset'] not in datasets]
    else:
        fields=list(rows[0]);old=[]
    combined=rows+old
    combined.sort(key=lambda r: {'corn':0,'tablet':1}[r['dataset']])
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({k:('' if not isinstance(v,str) and pd.isna(v) else v) for k,v in r.items()} for r in combined)

def load_data(datasets=('corn','tablet')):
    a=loadmat(ROOT/'data/data1_corn.mat',squeeze_me=True,struct_as_record=False)
    b=loadmat(ROOT/'data/data2_nir_shootout_2002.mat')
    sets={
      'corn': dict(X=np.asarray(a['m5spec'].data,dtype=float),y=np.asarray(a['propvals'].data[:,1],dtype=float),wavelength=np.asarray(a['m5spec'].axisscale[1,0],dtype=float),source=['corn']*80,row=np.arange(1,81),target='Oil',unit='original reference units'),
      'tablet': dict(X=np.vstack([b[x+'_1'][:,:597] for x in ['calibrate','validate','test']]),y=np.concatenate([b[x+'_Y'][:,2] for x in ['calibrate','validate','test']]),wavelength=np.arange(600,1794,2,dtype=float),source=sum(([x]*len(b[x+'_1']) for x in ['calibrate','validate','test']),[]),row=np.concatenate([np.arange(1,len(b[x+'_1'])+1) for x in ['calibrate','validate','test']]),target='API assay',unit='original reference units')}
    sets={name:sets[name] for name in datasets}
    audit=[]
    for name,d in sets.items():
        n,p=d['X'].shape
        assert np.isfinite(d['X']).all() and np.isfinite(d['y']).all()
        order=np.argsort(d['y'],kind='stable')
        d['cal']=order[np.arange(n)%4!=3]; d['pred']=order[np.arange(n)%4==3]
        rank=np.empty(n,int);rank[order]=np.arange(1,n+1)
        split=np.array(['calibration']*n,dtype=object);split[d['pred']]='prediction'
        outer_fold=np.zeros(n,int);tuning_fold=np.zeros(n,int)
        for fi,(_,va) in enumerate(folds(len(d['cal']),5)):
            outer_fold[d['cal'][va]]=fi+1
        for fi,(_,va) in enumerate(folds(len(d['cal']),4)):
            tuning_fold[d['cal'][va]]=fi+1
        pd.DataFrame(dict(id=np.arange(1,n+1),source_group=d['source'],source_row=d['row'],target=d['y'],sorted_rank=rank,partition=split,outer_cv_fold=outer_fold,full_calibration_tuning_cv_fold=tuning_fold)).to_csv(RES/f'{name}_split.csv',index=False)
        np.savez_compressed(RES/f'{name}_data.npz',**{k:d[k] for k in ['X','y','wavelength','cal','pred']})
        blocks=pywt.wavedec(d['X'][:1],'db4',level=3,mode='periodization',axis=1)
        metadata=[];offset=0
        for band,block in zip(['A3','D3','D2','D1'],blocks):
            for j in range(block.shape[1]):
                metadata.append(dict(coefficient_index_0=offset+j,coefficient_index_1=offset+j+1,band=band,band_index_1=j+1))
            offset+=block.shape[1]
        pd.DataFrame(metadata).to_csv(RES/f'{name}_wavelet_metadata.csv',index=False)
        for part,ii in [('All',np.arange(n)),('Calibration',d['cal']),('Prediction',d['pred'])]:
            y=d['y'][ii]
            audit.append(dict(dataset=name,partition=part,n=len(ii),p=p,target=d['target'],minimum=y.min(),maximum=y.max(),mean=y.mean(),sd=y.std(ddof=1)))
    merge_dataset_rows(audit,RES/'dataset_summary.csv',datasets)
    return sets

def preprocess(A,B,name):
    """Fit learned quantities on A only. Both returned matrices are uncentered."""
    if name=='Raw': return A.copy(),B.copy()
    if name=='SNV':
        def f(X): return (X-X.mean(1,keepdims=True))/np.maximum(X.std(1,ddof=1,keepdims=True),1e-15)
    elif name=='MSC':
        ref=A.mean(0);rc=ref-ref.mean();den=rc@rc
        def f(X):
            slope=(X-X.mean(1,keepdims=True))@rc/den
            if np.any(np.abs(slope)<1e-12): raise ValueError('Degenerate MSC slope')
            intercept=X.mean(1)-slope*ref.mean()
            return (X-intercept[:,None])/slope[:,None]
    elif name=='D1':
        def f(X): return savgol_filter(X,15,2,deriv=1,delta=2.,axis=1,mode='interp')
    elif name=='CWT':
        def f(X):
            pad=64
            Y=np.pad(X,((0,0),(pad,pad)),mode='symmetric')
            return pywt.cwt(Y,[8.],'gaus1',axis=1,method='conv')[0][0,:,pad:-pad]
    else: raise ValueError(name)
    return f(A),f(B)

def dwt(X):
    return np.concatenate(pywt.wavedec(X,'db4',level=3,mode='periodization',axis=1),axis=1)

def pls_path(X,y,maxlv=MAXLV):
    """Mean-centered PLS1 NIPALS, every coefficient path (no autoscaling)."""
    xm=X.mean(0);ym=float(y.mean());E=np.asarray(X-xm,order='C');f=y-ym
    n,p=X.shape;a=min(maxlv,n-2,p)
    W=[];P=[];C=[];betas=[]
    for _ in range(a):
        w=E.T@f;norm=np.linalg.norm(w)
        if norm<1e-24: break
        w/=norm;t=E@w;tt=t@t
        if tt<1e-24: break
        pp=E.T@t/tt;c=float(f@t/tt)
        W.append(w);P.append(pp);C.append(c)
        ww=np.column_stack(W);ppp=np.column_stack(P)
        coef=ww@np.linalg.solve(ppp.T@ww,np.array(C))
        betas.append(coef)
        E-=np.outer(t,pp);f-=c*t
    if not betas: betas=[np.zeros(p)]
    return xm,ym,np.stack(betas,axis=1)

def predict_path(model,X,maxlv=MAXLV):
    xm,ym,coef=model
    pred=(X-xm)@coef+ym
    if pred.shape[1]<maxlv: pred=np.column_stack([pred,np.repeat(pred[:,-1:],maxlv-pred.shape[1],axis=1)])
    return pred[:,:maxlv]

def folds(n,k=4,seed=SEED): return list(KFold(k,shuffle=True,random_state=seed).split(np.arange(n)))

def base_cv(X,y,prep,seed=SEED,k=4):
    out=np.empty((len(y),MAXLV));loss=[]
    for tr,va in folds(len(y),k,seed):
        A,B=preprocess(X[tr],X[va],prep)
        out[va]=predict_path(pls_path(A,y[tr]),B)
        loss.append(np.mean((out[va]-y[va,None])**2,axis=0))
    mse=np.mean((out-y[:,None])**2,axis=0)
    best=int(np.argmin(mse));se=np.std(np.array(loss)[:,best],ddof=1)/np.sqrt(k)
    lv=int(np.flatnonzero(mse<=mse[best]+se)[0]+1)
    return dict(preprocessing=prep,lv=lv,minimum_lv=best+1,rmsecv=float(np.sqrt(mse[lv-1])),curve=np.sqrt(mse),oof=out[:,lv-1],mse=mse,se=se)

def reliability(X,y,seed=SEED):
    rng=np.random.default_rng(seed);n,p=X.shape
    co=[]
    for _ in range(MC_RUNS):
        ii=rng.choice(n,max(SELECTOR_LV+2,n//2),replace=False)
        co.append(pls_path(X[ii],y[ii],SELECTOR_LV)[2][:,-1])
    co=np.array(co)
    sd=co.std(0,ddof=1);eps=np.finfo(float).eps*max(float(sd.max()),1e-30)
    classic=np.abs(co.mean(0))/(sd+eps)
    med=np.median(co,axis=0);mad=1.4826*np.median(np.abs(co-med),axis=0)
    robust=np.abs(med)/(mad+eps)*np.abs(np.sign(co).mean(0))
    positive=robust[robust>0];scale=float(np.median(positive)) if len(positive) else 1.
    weight=robust/(robust+scale+eps)
    return dict(classic=classic,robust=robust,weight=weight,coef=co)

def gain_order(X,y,weight,tau,maxk):
    R=X-X.mean(0);e=y-y.mean();norm2=np.sum(R*R,axis=0)
    penalty=tau*norm2*(1-weight)/np.maximum(weight,1e-12)
    used=np.zeros(X.shape[1],bool);sel=[]
    tol=np.finfo(float).eps*max(float(norm2.max()),1e-30)*max(X.shape)
    for _ in range(min(maxk,len(y)-2,X.shape[1])):
        den=np.sum(R*R,axis=0);g=(R.T@e)**2/np.maximum(den+penalty,1e-300)
        g[used|(den<=tol)]=-np.inf
        j=int(np.argmax(g))
        if not np.isfinite(g[j]): break
        sel.append(j);used[j]=True
        u=R[:,j]/np.sqrt(den[j]);R-=np.outer(u,u@R);e-=u*(u@e)
        # one reorthogonalization against new direction limits floating drift
        R-=np.outer(u,u@R)
    return np.array(sel,dtype=int)

def uve_sets(X,y,seed):
    n,p=X.shape;rng=np.random.default_rng(seed)
    N=rng.uniform(-1,1,(n,p))*1e-11
    Z=np.column_stack([X,N]);co=[]
    for i in range(n):
        ii=np.arange(n)!=i
        co.append(pls_path(Z[ii],y[ii],SELECTOR_LV)[2][:,-1])
    co=np.array(co);sd=co.std(0,ddof=1)
    # Per-column relative floor preserves tiny artificial-noise coefficients.
    rel=np.abs(co.mean(0))/np.maximum(sd,np.finfo(float).tiny)
    maxnoise=float(rel[p:].max());sets={}
    for m in UVE_MULT:
        s=np.flatnonzero(rel[:p]>m*maxnoise)
        if not len(s): s=np.array([int(np.argmax(rel[:p]))])
        sets[str(m)]=s
    return sets,rel[:p],maxnoise

def grid_k(p,n,method):
    limit=min(p,n-2) if 'CG-' in method or method=='GAIN' else p
    return sorted(set([k for k in KGRID if k<=limit]+[limit]))

def make_sets(A,y,method,seed,ks=None):
    if method=='PLS': return {'all':np.arange(A.shape[1])},{}
    if method=='UVE':
        s,rel,cut=uve_sets(A,y,seed)
        return s,dict(classic=rel,noise_max=cut)
    rr=reliability(A,y,seed)
    if method=='GAIN':
        rr['weight']=np.ones(A.shape[1])
    ks=ks or grid_k(A.shape[1],len(y),method)
    sets={}
    if method in ('MC-UVE','WT-MC-UVE','ROBUST'):
        order=np.argsort(-rr['robust' if method=='ROBUST' else 'classic'],kind='stable')
        for k in ks: sets[f'{k}']=order[:k]
    else:
        for tau in ([0.] if method=='GAIN' else TAUS):
            order=gain_order(A,y,np.ones(A.shape[1]) if method=='GAIN' else rr['weight'],tau,max(ks))
            for k in ks: sets[f'{tau}:{k}']=order[:min(k,len(order))]
    return sets,rr

def transform_train_test(X,Z,prep,method):
    A,B=preprocess(X,Z,prep)
    if method.startswith('WT-'): A,B=dwt(A),dwt(B)
    return A,B

def tune(X,y,prep,method,seed=SEED,kfold=4):
    p=dwt(X[:1]).shape[1] if method.startswith('WT-') else X.shape[1]
    # All folds share feasible cardinalities; choose grid before looking at outcomes.
    mintrain=min(len(tr) for tr,va in folds(len(y),kfold,seed))
    ks=grid_k(p,mintrain,method)
    records={};counts={};foldloss={}
    for fi,(tr,va) in enumerate(folds(len(y),kfold,seed)):
        A,B=transform_train_test(X[tr],X[va],prep,method)
        ss,_=make_sets(A,y[tr],method,seed+1000+fi,ks)
        for key,s in ss.items():
            pred=predict_path(pls_path(A[:,s],y[tr]),B[:,s])
            if key not in records:
                records[key]=np.empty((len(y),MAXLV));counts[key]=[];foldloss[key]=[]
            records[key][va]=pred;counts[key].append(len(s))
            foldloss[key].append(np.mean((pred-y[va,None])**2,axis=0))
    options=[]
    for key,pr in records.items():
        mse=np.mean((pr-y[:,None])**2,axis=0)
        for a in range(min(MAXLV,min(counts[key]))):
            options.append(dict(key=key,lv=a+1,mse=float(mse[a]),nvar=float(np.mean(counts[key])),se=float(np.std(np.array(foldloss[key])[:,a],ddof=1)/np.sqrt(kfold))))
    best=min(options,key=lambda o:o['mse']);threshold=best['mse']+best['se']
    # Same one-standard-error principle for every competing method.
    eligible=[o for o in options if o['mse']<=threshold]
    chosen=min(eligible,key=lambda o:(o['nvar'],o['lv'],o['mse']))
    return dict(**chosen,tuning_rmsecv=float(np.sqrt(chosen['mse'])),minimum_rmsecv=float(np.sqrt(best['mse'])),threshold_mse=threshold,curve=[dict(key=o['key'],lv=o['lv'],nvar=o['nvar'],rmsecv=np.sqrt(o['mse'])) for o in options],ks=ks)

def fit_predict(X,y,Z,prep,method,choice,seed=SEED):
    A,B=transform_train_test(X,Z,prep,method)
    ss,rr=make_sets(A,y,method,seed+1000,choice['ks'])
    s=ss[choice['key']];model=pls_path(A[:,s],y,choice['lv'])
    pred=predict_path(model,B[:,s],choice['lv'])[:,-1]
    calpred=predict_path(model,A[:,s],choice['lv'])[:,-1]
    return pred,calpred,s,rr,ss,A,B

def evaluate(y,pred):
    er=pred-y;rmse=float(np.sqrt(np.mean(er**2)))
    return dict(RMSEP=rmse,RPD=float(y.std(ddof=1)/rmse),R2_prediction=float(1-np.sum(er**2)/np.sum((y-y.mean())**2)),bias=float(er.mean()),SEP=float(np.std(er,ddof=1)),MAE=float(np.mean(np.abs(er))))

def stage_preprocess(data):
    rows=[]
    for name,d in data.items():
        X=d['X'][d['cal']];y=d['y'][d['cal']];Z=d['X'][d['pred']];z=d['y'][d['pred']]
        allr=[base_cv(X,y,p,SEED) for p in PRE]
        curves={}
        for p,r in zip(PRE,allr):
            oof=np.empty(len(y));lvs=[]
            for fi,(tr,va) in enumerate(folds(len(y),5)):
                inner=base_cv(X[tr],y[tr],p,SEED+fi+17)
                A,B=preprocess(X[tr],X[va],p)
                oof[va]=predict_path(pls_path(A,y[tr],inner['lv']),B,inner['lv'])[:,-1];lvs.append(inner['lv'])
            A,B=preprocess(X,Z,p)
            pred=predict_path(pls_path(A,y,r['lv']),B,r['lv'])[:,-1]
            row=dict(dataset=name,preprocessing=p,LV=r['lv'],n_variables=X.shape[1],RMSECV=float(np.sqrt(np.mean((oof-y)**2))),tuning_RMSECV=r['rmsecv'],**evaluate(z,pred))
            rows.append(row);curves[p]=r['curve']
            np.savez_compressed(RES/f'{name}_{p}_preprocess.npz',cal_spectra=A,pred_spectra=B,prediction=pred,oof=oof,lv_curve=r['curve'])
            print('PRE',row,flush=True)
        best=min((r for r in rows if r['dataset']==name),key=lambda r:r['RMSECV'])
        dump(dict(best=best['preprocessing'],lv=best['LV'],RMSECV=best['RMSECV'],selection='minimum Table 2 five-fold outer RMSECV; four-fold inner LV tuning',downstream_validation='fixed preprocessing; nested selector/LV tuning; conditional on preprocessing selection'),RES/f'{name}_preprocessing_choice.json')
        np.savez_compressed(RES/f'{name}_preprocessing_curves.npz',**curves)
        merge_dataset_rows([r for r in rows if r['dataset']==name],RES/'preprocessing_comparison.csv',[name])

def stage_main(data,methods=METHODS,resume=False):
    rows=[];audit=[]
    table_path=RES/('ablation_comparison.csv' if any(m in ['ROBUST','GAIN'] for m in methods) else 'model_comparison.csv')
    if table_path.exists(): rows=pd.read_csv(table_path,float_precision='round_trip').to_dict('records')
    for name,d in data.items():
        X=d['X'][d['cal']];y=d['y'][d['cal']];Z=d['X'][d['pred']];z=d['y'][d['pred']]
        prep=json.loads((RES/f'{name}_preprocessing_choice.json').read_text())['best']
        # Stage 1 is complete: all selectors use the representation chosen from
        # the per-preprocessing RMSECV table. This outer loop assesses only the
        # downstream selector/LV procedure, conditional on that representation.
        for method in methods:
            savekey=method.replace('-','_')
            if resume and (RES/f'{name}_{savekey}_final.npz').exists():
                print('SKIP existing',name,method,flush=True);continue
            st=time.time();oof=np.empty(len(y));outer=[]
            for fi,(tr,va) in enumerate(folds(len(y),5)):
                op=prep
                choice=tune(X[tr],y[tr],op,method,SEED+fi+17)
                pr,_,s,*_=fit_predict(X[tr],y[tr],X[va],op,method,choice,SEED+fi+17)
                oof[va]=pr
                outer.append(dict(fold=fi+1,preprocessing=op,key=choice['key'],lv=choice['lv'],nvar=len(s),tuning_rmsecv=choice['tuning_rmsecv'],validation_rmse=float(np.sqrt(np.mean((pr-y[va])**2)))))
                print('OUTER',name,method,fi+1,round(time.time()-st,1),flush=True)
            choice=tune(X,y,prep,method)
            pred,calpred,s,rr,ss,A,B=fit_predict(X,y,Z,prep,method,choice)
            row=dict(dataset=name,method=method,preprocessing=prep,n_variables=len(s),LV=choice['lv'],parameter=choice['key'],RMSEC=float(np.sqrt(np.mean((calpred-y)**2))),RMSECV=float(np.sqrt(np.mean((oof-y)**2))),tuning_RMSECV=choice['tuning_rmsecv'],**evaluate(z,pred),seconds=time.time()-st)
            rows=[r for r in rows if not(r['dataset']==name and r['method']==method)]+[row]
            merge_dataset_rows([r for r in rows if r['dataset']==name],table_path,[name])
            dump(dict(choice=choice,outer_folds=outer,summary=row),RES/f'{name}_{savekey}_model.json')
            saved=dict(oof=oof,prediction=pred,cal_prediction=calpred,selected=s,cal_features=A,pred_features=B)
            for k,v in rr.items():
                if k!='coef': saved[k]=v
            np.savez_compressed(RES/f'{name}_{savekey}_final.npz',**saved)
            curve=[]
            for key,sk in ss.items():
                candidates=[r for r in choice['curve'] if r['key']==key]
                if not candidates: continue
                c=min(candidates,key=lambda r:r['rmsecv']);lv=c['lv']
                pp=predict_path(pls_path(A[:,sk],y,lv),B[:,sk],lv)[:,-1]
                curve.append(dict(key=key,n_variables=len(sk),LV=lv,RMSECV=c['rmsecv'],RMSEP=evaluate(z,pp)['RMSEP']))
            pd.DataFrame(curve).to_csv(RES/f'{name}_{savekey}_curve.csv',index=False)
            print('FINAL',row,flush=True)

def stage_repeat(data,runs=30):
    """Randomness audit with fixed full-calibration hyperparameters; repeat CV refits selector.
    Curve CV is conditional/fixed-grid, distinct from nested RMSECV in the primary table.
    """
    allmetrics=[]
    for name,d in data.items():
        X=d['X'][d['cal']];y=d['y'][d['cal']];Z=d['X'][d['pred']];z=d['y'][d['pred']]
        for method in ['MC-UVE','CG-MC-UVE','WT-MC-UVE','WT-CG-MC-UVE']:
            skey=method.replace('-','_');info=json.loads((RES/f'{name}_{skey}_model.json').read_text());choice=info['choice'];prep=info['summary']['preprocessing']
            A,B=transform_train_test(X,Z,prep,method);p=A.shape[1]
            preds=[];inc=np.zeros(p);curves=[];runrows=[]
            # Fixed cardinality/penalty/PLS LV from run0 calibration tuning.
            for run in range(runs):
                rseed=SEED+100000*run
                pp,_,sel,rr,sets,_,_=fit_predict(X,y,Z,prep,method,choice,rseed)
                preds.append(pp);inc[sel]+=1
                oof=np.empty(len(y));curvepred={}
                # Plot only the chosen tau for CG; all k retained.
                final_tau=choice['key'].split(':')[0] if ':' in choice['key'] else None
                keys=[k for k in sets if final_tau is None or k.split(':')[0]==final_tau]
                lvbykey={}
                for key in keys:
                    cc=[r for r in choice['curve'] if r['key']==key]
                    if cc: lvbykey[key]=min(cc,key=lambda r:r['rmsecv'])['lv'];curvepred[key]=np.empty(len(y))
                for fi,(tr,va) in enumerate(folds(len(y),4,SEED)):
                    aa,bb=transform_train_test(X[tr],X[va],prep,method)
                    subs,_=make_sets(aa,y[tr],method,rseed+1000+fi,choice['ks'])
                    for key in lvbykey:
                        si=subs[key];lv=lvbykey[key]
                        curvepred[key][va]=predict_path(pls_path(aa[:,si],y[tr],lv),bb[:,si],lv)[:,-1]
                    si=subs[choice['key']];lv=choice['lv']
                    oof[va]=predict_path(pls_path(aa[:,si],y[tr],lv),bb[:,si],lv)[:,-1]
                rrw=dict(dataset=name,method=method,run=run+1,n_variables=len(sel),LV=choice['lv'],conditional_RMSECV=float(np.sqrt(np.mean((oof-y)**2))),**evaluate(z,pp))
                runrows.append(rrw);allmetrics.append(rrw)
                for key in lvbykey:
                    si=sets[key];lv=lvbykey[key]
                    ep=predict_path(pls_path(A[:,si],y,lv),B[:,si],lv)[:,-1]
                    curves.append(dict(run=run+1,key=key,n_variables=len(si),LV=lv,RMSECV=float(np.sqrt(np.mean((curvepred[key]-y)**2))),RMSEP=evaluate(z,ep)['RMSEP']))
                print('REPEAT',name,method,run+1,flush=True)
                merge_dataset_rows([r for r in allmetrics if r['dataset']==name],RES/'repeat_metrics.csv',[name])
            np.savez_compressed(RES/f'{name}_{skey}_repeats.npz',predictions=np.array(preds),inclusion_frequency=inc/runs)
            pd.DataFrame(curves).to_csv(RES/f'{name}_{skey}_repeat_curves.csv',index=False)

def validate_implementation():
    from sklearn.cross_decomposition import PLSRegression
    rng=np.random.default_rng(91);X=rng.normal(size=(40,12));y=X[:,:4]@np.array([2.,-.3,1.,.7])+rng.normal(0,.1,40);Z=rng.normal(size=(5,12))
    for a in [1,3,6]:
        ours=predict_path(pls_path(X,y,a),Z,a)[:,-1]
        other=PLSRegression(n_components=a,scale=False).fit(X,y).predict(Z).ravel()
        assert np.max(np.abs(ours-other))<1e-8, (a,np.max(np.abs(ours-other)))
    # Exact scalar penalized gain is the objective reduction at its minimizer.
    r=rng.normal(size=40);e=rng.normal(size=40);lam=.4
    aa=(r@e)/(r@r+lam);gain=(r@e)**2/(r@r+lam)
    assert abs(e@e-(np.sum((e-aa*r)**2)+lam*aa*aa)-gain)<1e-10
    # A duplicated feature cannot add conditional rank after its twin is selected.
    XX=np.column_stack([X[:,0],X[:,0],X[:,1]])
    ss=gain_order(XX,y,np.ones(3),0.,3)
    assert not(0 in ss and 1 in ss)
    dump(dict(pls_sklearn_max_tolerance=1e-8,penalized_gain_identity=True,duplicate_rank_check=True),RES/'implementation_checks.json')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['all','audit','preprocess','main','repeat','ablations'],default='all');ap.add_argument('--runs',type=int,default=30);ap.add_argument('--datasets',nargs='+',choices=['corn','tablet'],default=['corn','tablet'],help='Recompute only these datasets; preserve other dataset artifacts and CSV rows.');ap.add_argument('--resume',action='store_true',help='Reuse existing main model files; omit for a complete recomputation.');a=ap.parse_args()
    validate_implementation();data=load_data(a.datasets)
    if a.stage in ['all','preprocess']:stage_preprocess(data)
    if a.stage in ['all','main']:stage_main(data,resume=a.resume)
    if a.stage=='ablations':stage_main(data,['ROBUST','GAIN'],resume=a.resume)
    if a.stage in ['all','repeat']:stage_repeat(data,a.runs)
    dump(dict(corn_spectral_field='m5spec.data',tablet_spectral_fields=['calibrate_1','validate_1','test_1'],seed=SEED,MC_submodels=MC_RUNS,MC_fraction=.5,selector_LV=SELECTOR_LV,maxLV=MAXLV,outer_folds=5,inner_folds=4,preprocessing=PRE,preprocessing_selection='minimum Table 2 RMSECV',downstream_validation='fixed preprocessing; nested selector/LV tuning; conditional on preprocessing selection',sg_window=15,sg_polynomial=2,cwt_wavelet='gaus1',cwt_scale=8,cwt_padding=64,dwt_wavelet='db4',dwt_level=3,dwt_mode='periodization',tau=TAUS,kgrid=KGRID,uve_multipliers=UVE_MULT,numpy=np.__version__,scipy=scipy.__version__,pywavelets=pywt.__version__),RES/'analysis_config.json')
if __name__=='__main__':main()
