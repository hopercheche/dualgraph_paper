"""Analyze faculty-derived paired outcomes; reject incomplete templates.

Example: python dualgraph_analysis.py dualgraph_outcomes.csv --output results.json
Preserve the highest independent participant/source-family unit in
independent_cluster_id. Prefixes, repeats and paraphrases are not new clusters.
This utility checks structure, not the clinical validity of faculty annotations.
"""
from pathlib import Path
import argparse,csv,json,math,random

ENDPOINTS=('role','assessment')

def load(path,expected_n):
    with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if len(rows)!=expected_n: raise ValueError(f'Expected {expected_n} attempted checkpoints, found {len(rows)}. Retain failed runs.')
    ids=set(); counts={c:0 for c in ('C1','C2','C3','C4')}
    for row in rows:
        key=row.get('checkpoint_id','').strip()
        if not key or key in ids:raise ValueError('Checkpoint IDs must be non-empty and unique.')
        ids.add(key)
        if row.get('station') not in counts:raise ValueError(f'{key}: invalid station.')
        counts[row['station']]+=1
        if not row.get('independent_cluster_id','').strip():raise ValueError(f'{key}: source/participant cluster ID is required.')
        if row.get('origin_real_or_constructed') not in ('real','constructed'):raise ValueError(f'{key}: record real or constructed origin.')
        for endpoint in ENDPOINTS:
            for mode in ('A','B'):
                field=f'{endpoint}_{mode}'
                if row.get(field) not in ('0','1'):raise ValueError(f'{key}: {field} must be faculty-derived 0/1, not blank.')
                row[field]=int(row[field])
        for mode in ('A','B'):
            field=f'{mode}_failure'
            if row.get(field) not in ('0','1'):raise ValueError(f'{key}: explicit failure flag required.')
            row[field]=int(row[field])
            if row[field] and any(row[f'{e}_{mode}'] for e in ENDPOINTS):raise ValueError(f'{key}: failed execution cannot pass an outcome.')
    if expected_n%4 or any(n!=expected_n//4 for n in counts.values()):raise ValueError(f'Frozen design expects balanced stations; found {counts}. Amend protocol explicitly instead of silently changing n.')
    return rows

def quantile(values,q):
    a=sorted(values);x=(len(a)-1)*q;lo=int(x);hi=min(lo+1,len(a)-1)
    return a[lo]*(hi-x)+a[hi]*(x-lo) if hi!=lo else a[lo]

def exact_mcnemar(b,c):
    n=b+c
    return min(1.0,2*sum(math.comb(n,i) for i in range(min(b,c)+1))/2**n) if n else 1.0

def analyze(rows,reps=10000,seed=20261008,independent=False):
    if reps<1000:raise ValueError('Use at least 1000 cluster-bootstrap resamples.')
    clusters={}
    for r in rows:clusters.setdefault(r['independent_cluster_id'],[]).append(r)
    if len(clusters)<2:raise ValueError('At least two independent source clusters are needed for a resampling interval.')
    if independent and len(clusters)!=len(rows):raise ValueError('Exact independent-pair test cannot be requested when clusters contain multiple checkpoints.')
    rng=random.Random(seed); groups=list(clusters.values()); n=len(rows)
    samples={e:[] for e in ENDPOINTS}
    for _ in range(reps):
        sampled=[r for group in rng.choices(groups,k=len(groups)) for r in group]
        for e in ENDPOINTS:samples[e].append(sum(r[e+'_B']-r[e+'_A'] for r in sampled)/len(sampled))
    outcomes={}
    for e in ENDPOINTS:
        a=sum(r[e+'_A'] for r in rows);b=sum(r[e+'_B'] for r in rows)
        a_only=sum(r[e+'_A']==1 and r[e+'_B']==0 for r in rows)
        b_only=sum(r[e+'_A']==0 and r[e+'_B']==1 for r in rows)
        out={'A_success':a,'B_success':b,'attempted_n':n,'A_rate':a/n,'B_rate':b/n,'B_minus_A':(b-a)/n,
             'paired_cells':{'both_pass':sum(r[e+'_A']==r[e+'_B']==1 for r in rows),'A_only':a_only,'B_only':b_only,'neither_pass':sum(r[e+'_A']==r[e+'_B']==0 for r in rows)},
             'paired_cluster_bootstrap_97_5_percent_interval':[quantile(samples[e],.0125),quantile(samples[e],.9875)]}
        if independent:out['exact_mcnemar_p']=exact_mcnemar(a_only,b_only);out['bonferroni_two_outcome_p']=min(1,2*out['exact_mcnemar_p'])
        outcomes[e]=out
    return {'status':'OBSERVATIONS_FROM_USER_SUPPLIED_FACULTY_DERIVED_FLAGS','checkpoint_count':n,'independent_cluster_count':len(groups),'bootstrap_repetitions':reps,'seed':seed,'outcomes':outcomes,
            'failures':{m:sum(r[m+'_failure'] for r in rows) for m in ('A','B')},
            'stations':{c:{'n':sum(r['station']==c for r in rows),**{e:{m:sum(r[e+'_'+m] for r in rows if r['station']==c) for m in ('A','B')} for e in ENDPOINTS}} for c in ('C1','C2','C3','C4')},
            'notes':['Intervals preserve A/B pairing and resample entire declared clusters.','Very few clusters or heterogeneous source types may yield unreliable bootstrap inference; treat as pilot evidence.','These calculations do not verify faculty provenance, establish learning gain or validate the full rubric.','97.5% difference intervals use Bonferroni coverage for two primary outcomes; no independent-pair p-value is generated by default.']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-n',type=int,default=120);p.add_argument('--reps',type=int,default=10000);p.add_argument('--seed',type=int,default=20261008);p.add_argument('--assume-independent',action='store_true')
    a=p.parse_args()
    try:r=analyze(load(a.input,a.expected_n),a.reps,a.seed,a.assume_independent)
    except (ValueError,OSError) as err:p.error(str(err))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2),encoding='utf-8');print(f'Saved {len(r["outcomes"])} outcome analyses for {r["checkpoint_count"]} checkpoints in {r["independent_cluster_count"]} clusters.')

if __name__=='__main__':main()
