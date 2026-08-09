#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean

ATLAS_ID='MARKET_STRUCTURE_PATTERN_ATLAS_V1'

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def f(r,k):
    try:return float(r[k])
    except:return float('nan')
def finite(*xs):return all(math.isfinite(x) for x in xs)
def bps(a,b):return (b/a-1.0)*10000.0 if finite(a,b) and a>0 else float('nan')

def load_rows(path:Path,instrument:str):
    with path.open(newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
    if not rows: raise ValueError('empty_dataset')
    cols=set(rows[0])
    generic={'timestamp','open','high','low','close'}
    prefix=instrument.lower()
    matrix={f'{prefix}_open',f'{prefix}_high',f'{prefix}_low',f'{prefix}_close'}
    if generic.issubset(cols):
        omap={'open':'open','high':'high','low':'low','close':'close'}
    elif matrix.issubset(cols):
        omap={x:f'{prefix}_{x}' for x in ('open','high','low','close')}
    else: raise ValueError('ohlc_schema_not_supported')
    out=[]
    for r in rows:
        ts=r['timestamp'];sess=r.get('session') or ts[:10]
        o,h,l,c=(f(r,omap[x]) for x in ('open','high','low','close'))
        if not finite(o,h,l,c) or min(o,h,l,c)<=0 or h<l: continue
        out.append({'timestamp':ts,'session':sess,'open':o,'high':h,'low':l,'close':c})
    out.sort(key=lambda x:x['timestamp'])
    return out

def confirm_pivots(rows,threshold_bps:float):
    if len(rows)<3:return []
    piv=[];direction=0
    extreme_i=0;extreme_price=rows[0]['close']
    seed_price=rows[0]['close']
    for i in range(1,len(rows)):
        r=rows[i]
        if r['session']!=rows[i-1]['session']:
            direction=0;extreme_i=i;extreme_price=r['close'];seed_price=r['close'];continue
        hi,lo=r['high'],r['low']
        if direction==0:
            up=bps(seed_price,hi);dn=bps(seed_price,lo)
            if up>=threshold_bps and up>=abs(dn):
                direction=1;extreme_i=i;extreme_price=hi
            elif dn<=-threshold_bps:
                direction=-1;extreme_i=i;extreme_price=lo
            continue
        if direction==1:
            prior_extreme_i=extreme_i;prior_extreme_price=extreme_price
            reversal=bps(prior_extreme_price,lo)
            if reversal<=-threshold_bps:
                piv.append({'type':'HIGH','pivot_index':prior_extreme_i,'pivot_timestamp':rows[prior_extreme_i]['timestamp'],'confirmation_index':i,'confirmation_timestamp':r['timestamp'],'price':prior_extreme_price,'threshold_bps':threshold_bps,'session':rows[prior_extreme_i]['session']})
                direction=-1;extreme_i=i;extreme_price=lo
            elif hi>=extreme_price:
                extreme_i=i;extreme_price=hi
        else:
            prior_extreme_i=extreme_i;prior_extreme_price=extreme_price
            reversal=bps(prior_extreme_price,hi)
            if reversal>=threshold_bps:
                piv.append({'type':'LOW','pivot_index':prior_extreme_i,'pivot_timestamp':rows[prior_extreme_i]['timestamp'],'confirmation_index':i,'confirmation_timestamp':r['timestamp'],'price':prior_extreme_price,'threshold_bps':threshold_bps,'session':rows[prior_extreme_i]['session']})
                direction=1;extreme_i=i;extreme_price=hi
            elif lo<=extreme_price:
                extreme_i=i;extreme_price=lo
    return piv

def bar_descriptors(rows,i,lookback):
    r=rows[i];o,h,l,c=r['open'],r['high'],r['low'],r['close'];rng=h-l
    body=abs(c-o);upper=h-max(o,c);lower=min(o,c)-l
    prior=[rows[j]['high']-rows[j]['low'] for j in range(max(0,i-lookback),i) if rows[j]['session']==r['session']]
    avg=mean(prior) if prior else None
    ret=bps(o,c)
    desc=[]
    if rng>0:
        if body/rng>=0.65 and c>o:desc.append('STRONG_BULL_BODY')
        if body/rng>=0.65 and c<o:desc.append('STRONG_BEAR_BODY')
        if upper/rng>=0.45:desc.append('UPPER_WICK_REJECTION')
        if lower/rng>=0.45:desc.append('LOWER_WICK_REJECTION')
    if avg and avg>0:
        ratio=rng/avg
        if ratio<=0.65:desc.append('RANGE_COMPRESSION')
        if ratio>=1.75:desc.append('RANGE_EXPANSION')
    return {'bar_return_bps':ret,'range':rng,'body_fraction':body/rng if rng>0 else None,'upper_wick_fraction':upper/rng if rng>0 else None,'lower_wick_fraction':lower/rng if rng>0 else None,'rolling_range_ratio':rng/avg if avg and avg>0 else None,'primitives':desc}

def classify_swings(pivots,tol_bps):
    last={'HIGH':None,'LOW':None};events=[];active_session=None
    for p in pivots:
        sess=p.get('session')
        if sess is None:raise ValueError('pivot_session_missing')
        if sess!=active_session:
            last={'HIGH':None,'LOW':None};active_session=sess
        prev=last[p['type']];labels=[]
        if prev:
            d=bps(prev['price'],p['price'])
            if p['type']=='HIGH':
                labels.append('HIGHER_HIGH' if d>tol_bps else 'LOWER_HIGH' if d<-tol_bps else 'DOUBLE_TOP_LIKE')
            else:
                labels.append('HIGHER_LOW' if d>tol_bps else 'LOWER_LOW' if d<-tol_bps else 'DOUBLE_BOTTOM_LIKE')
        events.append({**p,'swing_labels':labels})
        last[p['type']]=p
    return events

def build_zones(pivots,tol_bps,min_touches):
    zones=[]
    for p in pivots:
        side='RESISTANCE' if p['type']=='HIGH' else 'SUPPORT';matched=None
        for z in zones:
            if z['side']!=side:continue
            if abs(bps(z['center'],p['price']))<=tol_bps:matched=z;break
        if matched is None:
            matched={'zone_id':f'{side}_{len(zones)+1:04d}','side':side,'center':p['price'],'touches':0,'first_confirmation_timestamp':p['confirmation_timestamp'],'last_confirmation_timestamp':p['confirmation_timestamp'],'members':[]}
            zones.append(matched)
        matched['members'].append(p['price']);matched['touches']+=1;matched['center']=mean(matched['members']);matched['last_confirmation_timestamp']=p['confirmation_timestamp']
    return [z for z in zones if z['touches']>=min_touches]

def zone_events(rows,zones,tol_bps):
    out=[]
    for z in zones:
        active=False
        for i,r in enumerate(rows):
            if r['timestamp']<z['first_confirmation_timestamp']:continue
            dist=abs(bps(z['center'],r['close']))
            near=dist<=tol_bps
            if near and not active:
                out.append({'timestamp':r['timestamp'],'session':r['session'],'zone_id':z['zone_id'],'primitive':z['side']+'_ZONE_TOUCH','zone_center':z['center'],'close':r['close']});active=True
            elif not near:active=False
            if z['side']=='RESISTANCE' and bps(z['center'],r['close'])>tol_bps:
                out.append({'timestamp':r['timestamp'],'session':r['session'],'zone_id':z['zone_id'],'primitive':'RESISTANCE_BREAK','zone_center':z['center'],'close':r['close']});break
            if z['side']=='SUPPORT' and bps(z['center'],r['close'])<-tol_bps:
                out.append({'timestamp':r['timestamp'],'session':r['session'],'zone_id':z['zone_id'],'primitive':'SUPPORT_BREAK','zone_center':z['center'],'close':r['close']});break
    return out

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--input',required=True);ap.add_argument('--instrument',default='BANKNIFTY');ap.add_argument('--contract',default='research/strategy_certification/MARKET_STRUCTURE_PATTERN_ATLAS_V1.json');ap.add_argument('--output-dir',default='research/evidence/market_structure_pattern_atlas_v1');a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ip=Path(a.input);ip=ip if ip.is_absolute() else root/ip;cp=root/a.contract;od=root/a.output_dir
    res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'forward_profitability_labels_computed':False}
    try:
        contract=json.loads(cp.read_text())
        if contract.get('atlas_id')!=ATLAS_ID:raise ValueError('atlas_contract_mismatch')
        rows=load_rows(ip,a.instrument);thresholds=[float(x) for x in contract['zigzag_thresholds_bps']];tol=float(contract['zone_tolerance_bps']);mint=int(contract['zone_min_confirmed_touches']);look=int(contract['rolling_context_bars'])
        all_piv=[];all_zones=[];all_zone_events=[]
        for th in thresholds:
            pv=classify_swings(confirm_pivots(rows,th),tol);all_piv.extend(pv);zs=build_zones(pv,tol,mint)
            for z in zs:z['threshold_bps']=th
            all_zones.extend(zs);all_zone_events.extend(zone_events(rows,zs,tol))
        bar_events=[]
        for i,r in enumerate(rows):
            d=bar_descriptors(rows,i,look)
            for p in d.pop('primitives'):
                bar_events.append({'timestamp':r['timestamp'],'session':r['session'],'instrument':a.instrument,'primitive':p,**d})
        piv_events=[]
        for p in all_piv:
            piv_events.append({'timestamp':p['confirmation_timestamp'],'session':p['session'],'instrument':a.instrument,'primitive':'CONFIRMED_SWING_'+p['type'],'pivot_timestamp':p['pivot_timestamp'],'pivot_price':p['price'],'threshold_bps':p['threshold_bps']})
            for lab in p['swing_labels']:
                piv_events.append({'timestamp':p['confirmation_timestamp'],'session':p['session'],'instrument':a.instrument,'primitive':lab,'pivot_timestamp':p['pivot_timestamp'],'pivot_price':p['price'],'threshold_bps':p['threshold_bps']})
        episodes=sorted(piv_events+bar_events+[{**e,'instrument':a.instrument} for e in all_zone_events],key=lambda x:(x['timestamp'],x['primitive']))
        counts=Counter(e['primitive'] for e in episodes)
        od.mkdir(parents=True,exist_ok=True)
        ep=od/f'{a.instrument}_episodes.jsonl';zp=od/f'{a.instrument}_zones.json';sp=od/f'{a.instrument}_summary.json'
        ep.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in episodes));zp.write_text(json.dumps(all_zones,indent=2,sort_keys=True)+'\n')
        res.update({'status':'PATTERN_ATLAS_BUILD_COMPLETE','atlas_id':ATLAS_ID,'instrument':a.instrument,'input_path':str(ip),'input_sha256':sha256(ip),'contract_sha256':sha256(cp),'rows':len(rows),'sessions':len({r['session'] for r in rows}),'thresholds_bps':thresholds,'confirmed_pivots':len(all_piv),'zones':len(all_zones),'episodes':len(episodes),'primitive_counts':dict(sorted(counts.items())),'episodes_path':str(ep),'episodes_sha256':sha256(ep),'zones_path':str(zp),'zones_sha256':sha256(zp),'swing_label_scope':'SESSION_LOCAL','interpretation':'Descriptive causal structure atlas only. Swing labels reset at every trading-session boundary. No trading edge or forward profitability is claimed.'})
    except Exception as e:res['error']=f'{type(e).__name__}:{e}'
    od.mkdir(parents=True,exist_ok=True);sp=od/f'{a.instrument}_summary.json';sp.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='PATTERN_ATLAS_BUILD_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
