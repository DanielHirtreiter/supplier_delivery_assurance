"""Supplier economic impact. One bounded disruption episode per supplier.

Shared Python/NumPy engine for native HTTP and browser Pyodide execution.
Loss = permanently lost contribution + penalties + incremental disruption cost.
Recoverable delayed revenue and expediting spend are reported separately.
"""
import hashlib
import copy
import json
import math
import platform
from pathlib import Path
import numpy as np
import scipy
from scipy import stats
from mc_core import loss_summary, mean_interval, event_interval, empirical_var_es, bootstrap_tail_intervals

MODEL_VERSION='2.0.0'

def validate(config):
    if not isinstance(config,dict): raise ValueError('A configuration object is required.')
    for key,lo,hi in [('n',2000,100000),('seed',0,4294967295)]:
        v=config.get(key)
        if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi: raise ValueError(f'{key} must be an integer from {lo} to {hi}.')
    def number(obj,key,lo,hi):
        v=obj.get(key)
        if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not lo<=v<=hi: raise ValueError(f'{key} must be a finite number from {lo} to {hi}.')
    for key,lo,hi in [('threshold',0,1e9),('mean_tolerance',1,1e6),('common_probability',0,1),('common_days',0,84)]: number(config,key,lo,hi)
    rows=config.get('suppliers')
    if not isinstance(rows,list) or not 1<=len(rows)<=20: raise ValueError('Provide 1–20 supplier assumptions.')
    ids=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in ids: raise ValueError('Suppliers must have unique IDs.')
        ids.add(row['id'])
        if not isinstance(row.get('name'),str) or len(row['name'])>200: raise ValueError('Invalid supplier name.')
        if not isinstance(row.get('enabled'),bool): raise ValueError('Supplier inclusion must be true or false.')
        for key in ['probability','cancel_low','cancel_mode','cancel_high','success']: number(row,key,0,1)
        for key in ['delay_low','delay_mode','delay_high','buffer_days','saved_days','lead_days']: number(row,key,0,84)
        for key in ['exposed_units','capacity_units']: number(row,key,0,1e7)
        number(row,'daily_demand',.01,1e6)
        for key in ['price','margin','penalty','extra_cost_day','fixed_cost','premium_unit']: number(row,key,0,1e6)
        if row['margin']>row['price']: raise ValueError('Contribution margin cannot exceed selling price in this model.')
        for prefix in ['delay','cancel']:
            if not row[prefix+'_low']<=row[prefix+'_mode']<=row[prefix+'_high']: raise ValueError(f'{row["name"]}: {prefix} must satisfy minimum ≤ mode ≤ maximum.')
    if not any(row['enabled'] for row in rows): raise ValueError('Include at least one supplier.')
    return config

def triangular(u,low,mode,high):
    if high==low:return np.full_like(u,float(low))
    f=(mode-low)/(high-low)
    return np.where(u<f,low+np.sqrt(u*(high-low)*(mode-low)),high-np.sqrt((1-u)*(high-low)*(high-mode)))

def sample(config,n,rng):
    """Independent scenario rows, fixed draw order; one common stress per row."""
    rows=[r for r in config['suppliers'] if r['enabled']]
    return {'common':rng.random(n)<config['common_probability'],
            'primitive':rng.random((len(rows),4,n))}

def evaluate(config,draws,force_stress=False):
    """Deterministic evaluation of shared primitive draws; no RNG inside."""
    rows=[r for r in config['suppliers'] if r['enabled']]
    n=len(draws['common']); shape=(n,len(rows))
    gross=np.zeros(shape);net=np.zeros(shape);components=np.zeros((len(rows),4));delayed=np.zeros(shape)
    delays=np.zeros(shape);cancellations=np.zeros(shape);improvements=np.zeros(shape)
    common=np.ones(n,dtype=bool) if force_stress else draws['common']
    for j,row in enumerate(rows):
        u=draws['primitive'][j];event=u[0]<row['probability']
        duration=np.minimum(84,triangular(u[1],row['delay_low'],row['delay_mode'],row['delay_high'])+common*config['common_days'])
        delay=event*duration
        cancel=triangular(u[2],row['cancel_low'],row['cancel_mode'],row['cancel_high'])
        days=np.maximum(0,delay-row['buffer_days'])
        affected=np.minimum(row['exposed_units'],row['daily_demand']*days)
        # Expediting cannot arrive before its lead time or exceed recovery capacity.
        triggered=affected>0
        success=triggered&(u[3]<row['success'])
        potential=np.maximum.reduce([np.full(n,row['lead_days']),delay-row['saved_days'],delay-row['capacity_units']/row['daily_demand']])
        residual_delay=np.where(success,np.minimum(delay,potential),delay)
        residual_days=np.maximum(0,residual_delay-row['buffer_days'])
        residual_units=np.minimum(row['exposed_units'],row['daily_demand']*residual_days)
        recovered=affected-residual_units
        cost=triggered*row['fixed_cost']+recovered*row['premium_unit']
        lost=affected*cancel*row['margin']
        penalty=affected*days*row['penalty']
        extra=np.where(affected>0,days*row['extra_cost_day'],0)
        gross[:,j]=lost+penalty+extra
        net[:,j]=residual_units*cancel*row['margin']+residual_units*residual_days*row['penalty']+np.where(residual_units>0,residual_days*row['extra_cost_day'],0)+cost
        delayed[:,j]=affected*(1-cancel)*row['price']
        components[j]=[lost.mean(),penalty.mean(),extra.mean(),cost.mean()]
        delays[:,j]=delay;cancellations[:,j]=cancel;improvements[:,j]=recovered
    assert np.all(np.isfinite(gross)) and np.all(gross>=0)
    assert np.all(np.isfinite(net)) and np.all(net>=0)
    return dict(gross=gross,net=net,components=components,delayed=delayed,delays=delays,cancellations=cancellations,recovered=improvements)

def distribution(values,maximum):
    counts,edges=np.histogram(values,bins=36,range=(0,max(1,maximum)))
    return {'counts':counts.tolist(),'edges':edges.tolist(),'cdf':[{'x':float(x),'probability':float(p)} for p,x in zip(np.linspace(0,1,101),np.quantile(values,np.linspace(0,1,101),method='inverted_cdf'))]}

def association(x,y):
    return float(stats.spearmanr(x,y).statistic) if np.ptp(x)>0 and np.ptp(y)>0 else None

def run(config):
    config=validate(config)
    rows=[r for r in config['suppliers'] if r['enabled']]
    streams=np.random.SeedSequence(config['seed']).spawn(3)
    pilot=evaluate(config,sample(config,1000,np.random.default_rng(streams[0])))['gross'].sum(axis=1)
    recommended=max(2000,math.ceil((1.96*float(pilot.std(ddof=1))/config['mean_tolerance'])**2),9604)
    rng=np.random.default_rng(streams[1]);draws=sample(config,config['n'],rng);e=evaluate(config,draws)
    total=e['gross'].sum(axis=1);net=e['net'].sum(axis=1);threshold=config['threshold'];maximum=float(max(total.max(),net.max(),1))
    baseline=loss_summary(total,threshold=threshold);mitigated=loss_summary(net,threshold=threshold)
    tail=bootstrap_tail_intervals(total,np.random.default_rng(streams[2]),resamples=100)
    q=baseline['var'];weights=(total>q).astype(float);ties=total==q
    if ties.sum():weights[ties]=max(0,(len(total)*.05-weights.sum())/ties.sum())
    contribution=(e['gross']*weights[:,None]).mean(axis=0)/.05
    supplier=[]
    for j,row in enumerate(rows):
        supplier.append({'id':row['id'],'name':row['name'],'baseline':loss_summary(e['gross'][:,j],threshold=threshold),
          'mitigated':loss_summary(e['net'][:,j],threshold=threshold),'net_saving':mean_interval(e['gross'][:,j]-e['net'][:,j]),
          'tail_contribution':float(contribution[j]),'mean_lost_contribution':float(e['components'][j,0]),'mean_penalty':float(e['components'][j,1]),
          'mean_extra_cost':float(e['components'][j,2]),'mean_expediting_cost':float(e['components'][j,3]),
          'mean_delayed_revenue':float(e['delayed'][:,j].mean()),'mean_recovered_units':float(e['recovered'][:,j].mean()),
          'delay_association':association(e['delays'][:,j],e['gross'][:,j]),'cancellation_association':association(e['cancellations'][:,j],e['gross'][:,j]),
          'distribution':distribution(e['gross'][:,j],max(float(e['gross'][:,j].max()),float(e['net'][:,j].max()),1)),
          'mitigated_distribution':distribution(e['net'][:,j],max(float(e['gross'][:,j].max()),float(e['net'][:,j].max()),1))})
    assert np.isclose(contribution.sum(),baseline['es'])
    assert np.isclose(sum(x['baseline']['mean']['mean'] for x in supplier),baseline['mean']['mean'])
    joint=evaluate(config,draws,force_stress=True)['gross'].sum(axis=1)
    assumption_stress=[]
    for kind,label in [('delay','Delay upper bounds +50% (capped at 84 days)'),('cancel','Cancellation fractions fixed at their upper bounds'),('margin','Contribution margins −25%')]:
        variant=copy.deepcopy(config)
        for row in variant['suppliers']:
            if kind=='delay':row['delay_high']=min(84,row['delay_high']*1.5)
            elif kind=='cancel':row['cancel_low']=row['cancel_mode']=row['cancel_high']
            else:row['margin']*=.75
        values=evaluate(variant,draws)['gross'].sum(axis=1)
        assumption_stress.append({'label':label,'mean_loss':float(values.mean()),**empirical_var_es(values)})
    correlations=[]
    for a in range(len(rows)):
        correlations.append([float(np.corrcoef(e['gross'][:,a],e['gross'][:,b])[0,1]) if np.ptp(e['gross'][:,a])>0 and np.ptp(e['gross'][:,b])>0 else None for b in range(len(rows))])
    code_hash=hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('mc_core.py').read_bytes()).hexdigest()
    mean_half=(baseline['mean']['ci'][1]-baseline['mean']['ci'][0])/2
    return {'model_version':MODEL_VERSION,'config':config,'baseline':baseline,'mitigated':mitigated,
      'net_saving':mean_interval(total-net),'probability_mitigation_better':event_interval(net<total),
      'suppliers':supplier,'distribution':distribution(total,maximum),'mitigated_distribution':distribution(net,maximum),
      'stress':{'mean_loss':float(joint.mean()),**empirical_var_es(joint)},'assumption_stress':assumption_stress,'tail_diagnostic':tail,
      'diagnostics':{'recommended_n_from_pilot':recommended,'pilot_n':1000,'mean_half_width':mean_half,
          'mean_precision_met':mean_half<=config['mean_tolerance'],'probability_half_width':(baseline['exceedance']['ci'][1]-baseline['exceedance']['ci'][0])/2,
          'tail_var_half_width':(tail['var_ci'][1]-tail['var_ci'][0])/2,'tail_es_half_width':(tail['es_ci'][1]-tail['es_ci'][0])/2,
          'realized_common_stress':event_interval(draws['common']),'supplier_loss_correlation':correlations,
          'common_stress_mean_loss':float(total[draws['common']].mean()) if draws['common'].any() else None},
      'reproducibility':{'seed':config['seed'],'n':config['n'],'bit_generator':type(rng.bit_generator).__name__,'python':platform.python_version(),
          'numpy':np.__version__,'scipy':scipy.__version__,'code_sha256':code_hash,
          'config_sha256':hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
          'sampling':'IID rows; SeedSequence children: independent pilot, production, tail bootstrap. Common primitive draws pair baseline and expediting.'},
      'limitations':['Synthetic, uncalibrated financial and delay inputs; intervals measure Monte Carlo sampling error, not confidence in the business assumptions.',
          'One pooled disruption episode per supplier over 84 days; no BOM, shared customer-order allocation, repeated events or intra-period cash-flow model.',
          'Supplier exposures must be disjoint for portfolio aggregation. Standalone supplier P95 values are not additive.',
          'Recovered delayed revenue is informational, not an additional loss. This is an incremental economic-loss model, not a quarterly profit or liquidity forecast.',
          'Duration is capped at 84 days; losses from unresolved recovery beyond that horizon are excluded. Common stress affects severity, not occurrence probability.']}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('config');parser.add_argument('--output',default='simulation-result.json')
    args=parser.parse_args();result=run(json.loads(Path(args.config).read_text()));Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False));print(args.output)
