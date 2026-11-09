"""High-glucose experiments using the original all-70kg GRU-Hovorka.
Warm-start from the original checkpoint; validation-only selection.
One 1.25x loss-weight trial with the original history encoding.
"""
import argparse
import copy
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

PARAM_NAMES = ['si1','si2','si3','tmax_i','tmax_g','egp0','f01']
NOMINAL = [0.00512,0.00082,0.052,55.,40.,0.0161,0.0097]
LOWER = [0.0002,0.00005,0.001,15.,10.,0.002,0.001]
UPPER = [0.02,0.005,0.1,180.,180.,0.05,0.03]
FEATURES = ['cgm_mg_dl','basal_rate_u_per_hour','bolus_u','carbs_g']
HISTORY = 288  # 24h, encoder aggregates to 15min; simulator uses last 6h
HORIZON = 24
FIXED = dict(weight_kg=70.,vg=0.16,vi=0.12,k12=0.066,ka1=0.006,
             ka2=0.06,ka3=0.03,ke=0.138,ag=0.8)


def read_data(path):
    d = pd.read_parquet(path)
    needed = ['dataset', 'patient_id', 'split', 'timestamp'] + FEATURES
    missing = set(needed) - set(d.columns)
    if missing:
        raise ValueError('Missing columns: ' + str(missing))
    d = d.sort_values(['dataset', 'patient_id', 'timestamp']).reset_index(drop=True)
    if d[needed].isna().any().any() or not np.isfinite(d[FEATURES].to_numpy()).all():
        raise ValueError('Missing/nonfinite input data')
    if (d[FEATURES].to_numpy() < 0).any() or (d.cgm_mg_dl <= 0).any():
        raise ValueError('Invalid negative inputs or nonpositive CGM')
    if d.duplicated(['dataset', 'patient_id', 'timestamp']).any():
        raise ValueError('Duplicate timestamps')
    labels = {}
    for key, g in d.groupby(['dataset', 'patient_id']):
        if g.split.nunique() != 1:
            raise ValueError('Patient crosses splits: ' + str(key))
        labels[str(key)] = g.split.iloc[0]
        if not g.timestamp.diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            raise ValueError('Patient has gaps: ' + str(key))
    if 'source_minute_count' in d and not d.source_minute_count.eq(5).all():
        raise ValueError('Remove/handle partial intervals first')
    return d, labels


def make_windows(d, split, start_day=0, end_day=100000, per_patient=0, seed=42):
    """Deterministically sample disjoint future windows per patient.

    All historical indices are strictly prior to, or at, forecast origin.
    end_day is exclusive: end_day=21 restricts all targets to the first 21d.
    """
    histories, inputs, targets, records = [], [], [], []
    rng = np.random.default_rng(seed)
    skipped = []
    for (dataset, pid), g in d[d.split == split].groupby(['dataset', 'patient_id']):
        g = g.reset_index(drop=True)
        a = g[FEATURES].to_numpy(dtype=np.float32)
        first = max(HISTORY, int(start_day * 288))
        stop = min(len(g), int(end_day * 288))
        origins = np.arange(first, stop-HORIZON, HORIZON)
        if not len(origins):
            skipped.append(str(dataset) + ':' + str(pid))
            continue
        if per_patient > 0 and len(origins) > per_patient:
            origins = np.sort(rng.choice(origins, per_patient, replace=False))
        for i in origins:
            # 24h of complete historical intervals, plus the forecast-origin observation.
            histories.append(a[i-HISTORY:i+1])
            inputs.append(a[i:i+HORIZON, 1:])  # basal U/hr, bolus U, carbs g
            targets.append(a[i+1:i+HORIZON+1, 0])
            records.append(dict(dataset=str(dataset), patient_id=str(pid),
                                origin=str(g.timestamp.iloc[i])))
    if not records:
        raise ValueError('No windows available for split ' + split)
    tensors = [torch.tensor(np.stack(z)) for z in (histories, inputs, targets)]
    return TensorDataset(*tensors), records, skipped


class ParameterGRU(nn.Module):
    def __init__(self,mean,scale,hidden=64,recent_raw=False):
        super().__init__()
        self.recent_raw=recent_raw
        self.register_buffer('mean',torch.as_tensor(mean,dtype=torch.float32))
        self.register_buffer('scale',torch.as_tensor(scale,dtype=torch.float32))
        self.register_buffer('lower',torch.tensor(LOWER).log())
        self.register_buffer('upper',torch.tensor(UPPER).log())
        self.gru=nn.GRU(4,hidden,num_layers=2,batch_first=True,dropout=0.1)
        self.head=nn.Sequential(nn.Linear(hidden*2,64),nn.SiLU(),nn.Linear(64,7))
        fraction=(torch.tensor(NOMINAL).log()-self.lower)/(self.upper-self.lower)
        nn.init.zeros_(self.head[-1].weight)
        with torch.no_grad():
            self.head[-1].bias.copy_(torch.logit(fraction))

    def forward(self,history):
        # Past 24h -> 96 15min bins; retain current observation separately.
        raw_steps=12 if self.recent_raw else 0
        older=history[:,:-1-raw_steps] if raw_steps else history[:,:-1]
        past=older.reshape(len(history),older.shape[1]//3,3,4)
        pooled=torch.stack((past[:,:,:,0].mean(2),past[:,:,:,1].mean(2),past[:,:,:,2].sum(2)/3,past[:,:,:,3].sum(2)/3),-1)
        features=torch.cat((pooled,history[:,-(raw_steps+1):]),1)
        output,_=self.gru((features-self.mean)/self.scale)
        encoding=torch.cat((output[:,-1],output.mean(1)),1)
        return torch.exp(self.lower+torch.sigmoid(self.head(encoding))*(self.upper-self.lower))


def derivatives(y: torch.Tensor, theta: torch.Tensor, basal: torch.Tensor, weight: float):
    """Same ten-state Hovorka equations as standalone hovorka.py, in torch."""
    q1,q2,s1,s2,ins,x1,x2,x3,d1,d2 = y.unbind(-1)
    si1, si2, si3, ti, tg, egp0, f01 = theta.unbind(-1)
    vg, vi = 0.16*weight, 0.12*weight
    glucose = q1/vg
    f01c = f01*weight*torch.minimum(glucose/4.5, torch.ones_like(glucose))
    renal = 0.003*torch.relu(glucose-9.0)*vg
    return torch.stack((
        -f01c-x1*q1+0.066*q2-renal+d2/tg+egp0*weight*(1-x3),
        x1*q1-(0.066+x2)*q2,
        basal*1000/60-s1/ti, (s1-s2)/ti, s2/(ti*vi)-0.138*ins,
        -0.006*x1+0.006*si1*ins,
        -0.06*x2+0.06*si2*ins,
        -0.03*x3+0.03*si3*ins,
        -d1/tg, (d1-d2)/tg), dim=-1)


def advance(y: torch.Tensor, theta: torch.Tensor, inputs: torch.Tensor, weight: float=70.0, substeps: int=5):
    basal, bolus, carbs = inputs.unbind(-1)
    event = torch.zeros_like(y)
    event[:, 2] = bolus*1000
    event[:, 8] = carbs*0.8*(1000/180.1559)
    y = y+event
    dt = 5.0/substeps
    for _ in range(substeps):
        k1 = derivatives(y,theta,basal,weight)
        k2 = derivatives(y+dt*k1/2,theta,basal,weight)
        k3 = derivatives(y+dt*k2/2,theta,basal,weight)
        k4 = derivatives(y+dt*k3,theta,basal,weight)
        y = y+dt*(k1+2*k2+2*k3+k4)/6
    return y


def simulate(history: torch.Tensor, future: torch.Tensor, theta: torch.Tensor, weight: float=70.0, substeps: int=5):
    """Return future glucose. No future glucose argument is accepted."""
    history=history[:,-73:]
    si1, si2, si3, ti, _, _, _ = theta.unbind(-1)
    u = history[:,0,1]*1000/60
    ins = u/(0.138*0.12*weight)
    x1,x2,x3 = si1*ins, si2*ins, si3*ins
    q1 = history[:,0,0]/18.01559*(0.16*weight)
    zero = torch.zeros_like(q1)
    y = torch.stack((q1,x1*q1/(0.066+x2),u*ti,u*ti,ins,x1,x2,x3,zero,zero),-1)
    # Historical observations initialize hidden state; they are available at origin.
    for k in range(history.shape[1]-1):
        y = advance(y,theta,history[:,k,1:],weight,substeps)
        q1_observed = history[:,k+1,0]/18.01559*(0.16*weight)
        y = torch.cat((q1_observed[:,None],y[:,1:]),dim=-1)
    predictions = []
    for k in range(future.shape[1]):
        y = advance(y,theta,future[:,k],weight,substeps)
        predictions.append(y[:,0]/(0.16*weight)*18.01559)
    return torch.stack(predictions,dim=1)


@torch.no_grad()
def validation_mae(model, ds, batch_size, weight, substeps):
    model.eval()
    total, count = 0.0, 0
    for h,u,g in DataLoader(ds,batch_size=batch_size):
        pred = simulate(h,u,model(h),weight,substeps)
        if not torch.isfinite(pred).all():
            raise RuntimeError('Nonfinite validation simulation')
        total += (pred-g).abs().sum().item()
        count += g.numel()
    return total/count


def sha256(path):
    digest = hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def metrics(pred,target):
    error=(pred-target).astype(np.float64);high=target>180;low=target<70;normal=~(low|high)
    result=dict(n=int(target.size),negative_prediction_count=int((pred<0).sum()),mae=float(np.abs(error).mean()),rmse=float(np.sqrt((error**2).mean())),mixed_accuracy=float(np.where(high,pred>180,np.abs(error)<22).mean()),high_recall=float((pred[high]>180).mean()) if high.any() else None,false_high_rate=float((pred[~high]>180).mean()) if (~high).any() else None)
    for name,mask in [('low',low),('normal',normal),('high',high)]:
        result[name+'_mae']=float(np.abs(error[mask]).mean()) if mask.any() else None;result[name+'_bias']=float(error[mask].mean()) if mask.any() else None;result[name+'_n']=int(mask.sum())
    positives=pred>180;result['high_precision']=float(high[positives].mean()) if positives.any() else None
    result['threshold_accuracy']=float((np.abs(error)<np.where(high,30.,22.)).mean())
    result['high_error_under_30_accuracy']=float((np.abs(error[high])<30).mean()) if high.any() else None
    result['balanced_mae']=float(np.mean([result[k+'_mae'] for k in ['low','normal','high'] if result[k+'_mae'] is not None]))
    return result

# Residual calibration: no GRU weight training occurs below.
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits


def feature_frame(history,pred,theta):
    h=history.numpy();x={};g=h[:,:,0]
    for lag in [0,1,3,6,12,24,48,72]:x[f'glucose_lag_{lag*5}min']=g[:,-1-lag]
    for steps in [3,6,12,24,48,72]:
        x[f'glucose_change_{steps*5}min']=g[:,-1]-g[:,-1-steps]
        x[f'glucose_mean_{steps*5}min']=g[:,-steps:].mean(1)
        x[f'glucose_std_{steps*5}min']=g[:,-steps:].std(1)
        for col,name in [(1,'basal'),(2,'bolus'),(3,'carbs')]:
            # Complete intervals before origin; current impulses kept separately.
            vals=h[:,-steps-1:-1,col]
            x[f'{name}_{steps*5}min']=vals.mean(1) if col==1 else vals.sum(1)
    for col,name in [(1,'basal'),(2,'bolus'),(3,'carbs')]:x[f'current_{name}']=h[:,-1,col]
    for k in [0,2,5,8,11]:x[f'baseline_{5*(k+1)}min']=pred[:,k]
    x['baseline_rise_60min']=pred[:,11]-g[:,-1]
    x['baseline_change_30_to_60']=pred[:,11]-pred[:,5]
    for k,name in enumerate(PARAM_NAMES):x['theta_'+name]=theta[:,k]
    return pd.DataFrame(x)


@torch.no_grad()
def generate(data,checkpoint,split):
    c=torch.load(checkpoint,map_location='cpu',weights_only=True)
    if sha256(data)!=c['data_sha256']:raise ValueError('Dataset differs from baseline')
    d,splits=read_data(data)
    if splits!=c['patient_splits']:raise ValueError('Patient splits changed')
    ds,records,_=make_windows(d,split)
    model=ParameterGRU(c['state_dict']['mean'],c['state_dict']['scale']);model.load_state_dict(c['state_dict']);model.eval()
    frames=[]
    for h,u,y in DataLoader(ds,batch_size=2048):
        theta=model(h);pred=simulate(h,u,theta,70.,5).numpy()
        f=feature_frame(h,pred,theta.numpy());f['target']=y[:,11].numpy();f['baseline']=pred[:,11];frames.append(f)
    frame=pd.concat(frames,ignore_index=True)
    ids=pd.DataFrame(records)
    return pd.concat([ids,frame],axis=1)


def feature_names(frame):return [k for k in frame if k not in ['dataset','patient_id','origin','target','baseline']]


def measure(pred,target):
    z=metrics(np.asarray(pred),np.asarray(target));hi=np.asarray(target)>180;ph=np.asarray(pred)>180
    z.update(false_high_count=int((ph&~hi).sum()),missed_high_count=int((~ph&hi).sum()))
    return z


def acceptable(m,b):
    return m['mae']<=b['mae']+.25 and m['high_mae']<=b['high_mae'] and m['low_mae']<=b['low_mae']+1 and m['normal_mae']<=b['normal_mae']+.5 and m['false_high_rate']<=b['false_high_rate']+.005


def make_regressor(depth):
    return HistGradientBoostingRegressor(loss='absolute_error',max_iter=120,learning_rate=.05,max_depth=depth,max_leaf_nodes=8,min_samples_leaf=100,l2_regularization=20.,early_stopping=False,random_state=42)



def rising_gate(frame,recent_threshold,forecast_threshold):
    # Zero below both thresholds; smoothly approaches one above either threshold.
    recent=np.clip((frame.glucose_change_15min.to_numpy()-recent_threshold)/10.,0.,1.)
    forecast=np.clip((frame.baseline_rise_60min.to_numpy()-forecast_threshold)/20.,0.,1.)
    return np.maximum(recent,forecast)


def predict_candidate(saved,frame):
    with threadpool_limits(limits=4):raw=saved['model'].predict(frame[saved['features']].to_numpy())
    gate=rising_gate(frame,saved['config']['recent_threshold'],saved['config']['forecast_threshold'])
    return saved['config']['alpha']*gate*np.clip(raw,-50.,50.),gate


def main():
    p=argparse.ArgumentParser();p.add_argument('data');p.add_argument('--checkpoint',default='baseline/model.pt');p.add_argument('--out',default='results');p.add_argument('--compile',action='store_true');p.add_argument('--retrain',action='store_true');a=p.parse_args()
    torch.set_num_threads(4)
    global advance
    if a.compile:advance=torch.compile(advance,dynamic=True)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if (out/'gated.joblib').exists() and not a.retrain:
        saved=joblib.load(out/'gated.joblib')
        if saved['checkpoint_sha256']!=sha256(a.checkpoint) or saved['data_sha256']!=sha256(a.data):raise ValueError('Source mismatch')
        print('Saved experiment reused.');return
    f=generate(a.data,a.checkpoint,'validation');f.to_parquet(out/'calibration.parquet',index=False)
    names=feature_names(f);X=f[names].to_numpy();y=(f.target-f.baseline).to_numpy();groups=f.patient_id.to_numpy()
    rising=(f.glucose_change_15min.to_numpy()>5.)|(f.baseline_rise_60min.to_numpy()>10.)
    base=measure(f.baseline,f.target);rows=[];oofs={}
    print('Calibration',len(f),'rising',int(rising.sum()),'rising eventual high',int((rising&(f.target>180)).sum()),flush=True)
    with threadpool_limits(limits=4):
        for depth in [2,3]:
            oof=np.zeros(len(f))
            for pid in sorted(set(groups)):
                train=(groups!=pid)&rising;hold=groups==pid
                if train.sum()<200:raise ValueError('Too few rising training windows')
                m=make_regressor(depth);m.fit(X[train],y[train]);oof[hold]=m.predict(X[hold])
            oofs[depth]=oof
            for recent,forecast in [(5.,10.),(10.,20.)]:
                gate=rising_gate(f,recent,forecast)
                for alpha in [.25,.5,.75,1.]:
                    correction=alpha*gate*np.clip(oof,-50.,50.);z=measure(f.baseline.to_numpy()+correction,f.target)
                    rows.append(dict(depth=depth,recent_threshold=recent,forecast_threshold=forecast,alpha=alpha,eligible=acceptable(z,base),gate_active_fraction=float((gate>0).mean()),**z))
            print('Completed patient-held-out CV for depth',depth,flush=True)
        improving=[r for r in rows if r['eligible'] and r['balanced_mae']<base['balanced_mae']-.05]
        eligible=[r for r in rows if r['eligible']]
        candidate=min(improving or eligible or rows,key=lambda r:r['balanced_mae'])
        selected=bool(improving);model=make_regressor(candidate['depth']);model.fit(X[rising],y[rising])
    payload=dict(model=model,features=names,config=candidate,enabled=selected,checkpoint_sha256=sha256(a.checkpoint),data_sha256=sha256(a.data),calibration_patients=sorted(set(groups)))
    joblib.dump(payload,out/'gated.joblib');pd.DataFrame(rows).to_csv(out/'cross_validation.csv',index=False)
    gate=rising_gate(f,candidate['recent_threshold'],candidate['forecast_threshold']);f['rising_training_window']=rising;f['oof_gate']=gate;f['oof_correction']=candidate['alpha']*gate*np.clip(oofs[candidate['depth']],-50.,50.);f['oof_candidate']=f.baseline+f.oof_correction;f.to_parquet(out/'calibration_oof.parquet',index=False)
    report=dict(baseline=base,candidate=candidate,enabled=selected,rising_calibration_windows=int(rising.sum()),total_calibration_windows=len(f),test_used_for_selection=False,protocol='Frozen baseline, six original validation patients, leave-one-patient-out residual CV; original baseline checkpoint selection used these patients. Expert training restricted to rises defined by observed history or baseline forecast, never future actual CGM.')
    (out/'selection.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
