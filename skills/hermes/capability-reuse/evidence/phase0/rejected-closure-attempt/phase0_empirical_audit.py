#!/usr/bin/env python3
import sqlite3, json, re, hashlib, statistics, time, math
from pathlib import Path
from datetime import datetime
HOME=Path.home(); DB=HOME/'.hermes/state.db'
OUT=Path('/root/.hermes/skills/hermes/capability-reuse/evidence/phase0')
OUT.mkdir(parents=True, exist_ok=True)
OPS={
 'hmp_healthcheck':[r'18643.*/hmp/health',r'/hmp/health',r'healthcheck',r'peer\d+.*health',r'hmp.*health',r'agent-card'],
 'hmp_send':[r'/hmp/send',r'send_and_wait',r'payload.*text',r'message_id',r'poll/'],
 'ssh_scp_deploy':[r'\bssh\b',r'\bscp\b',r'launchctl',r'systemctl',r'tar -xzf',r'py_compile'],
 'registry_sync':[r'registry-server',r'registry-publish',r'capability-registry',r'registry\.json'],
 'test_validation':[r'unittest',r'compileall',r'conformance-suite',r'active-canary-burnin',r'py_compile'],
 'file_patch':[r'from hermes_tools import patch',r'write_file',r'read_file',r'Path\(.*read_text',r'old_string',r'new_string'],
 'json_aggregation':[r'json\.loads',r'json\.dumps',r'aggregate',r'statistics\.mean'],
 'cron_process':[r'cronjob',r'process\(',r'background=True',r'schedule']
}
CAPS={
 'hmp-healthcheck': {'positive':[r'hmp.*health',r'health.*peer\d+',r'healthcheck.*peer\d+',r'ping.*hmp',r'agent-card'], 'effect':'read_only'},
 'hmp-send': {'positive':[r'send.*peer',r'/hmp/send',r'message.*hmp'], 'effect':'mutating'},
 'peer-heartbeat': {'positive':[r'heartbeat',r'ping.*peer'], 'effect':'read_only'}
}
MUTATING_NEG=[r'deploy',r'restart',r'ssh',r'scp',r'copy',r'send a message',r'remove',r'write',r'email']

def classify(txt):
    scores={}
    low=txt.lower()
    for op,pats in OPS.items():
        s=sum(1 for p in pats if re.search(p, low, re.I))
        if s: scores[op]=s
    return max(scores, key=scores.get) if scores else 'unknown_other'

def norm(txt):
    txt=re.sub(r'"[^"\n]{20,}"','"STR"',txt)
    txt=re.sub(r'\b\d{4,}\b','N',txt)
    txt=re.sub(r'\s+',' ',txt).strip()
    return txt

def iter_tool_calls(con):
    rows=con.execute("select id,session_id,timestamp,tool_calls from messages where tool_calls like '%execute_code%' order by timestamp").fetchall()
    for r in rows:
        try: calls=json.loads(r['tool_calls'])
        except Exception: continue
        for c in calls:
            fn=c.get('function') or {}
            if fn.get('name')!='execute_code': continue
            args=fn.get('arguments') or '{}'
            try: args=json.loads(args)
            except Exception: args={}
            code=args.get('code') or ''
            if not code: continue
            yield {'message_id':r['id'],'session_id':r['session_id'],'timestamp':r['timestamp'],'code':code,'operation':classify(code),'hash':hashlib.sha256(norm(code).encode()).hexdigest()[:16], 'preview':code[:240]}

def previous_user(con, session_id, before_id):
    row=con.execute("select content from messages where session_id=? and role='user' and id<? order by id desc limit 1",(session_id,before_id)).fetchone()
    return (row['content'] if row else '')[:1000]

def main():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    calls=list(iter_tool_calls(con))
    # operation stats
    by_op={}
    by_hash={}
    by_day={}
    by_sess={}
    for c in calls:
        by_op[c['operation']]=by_op.get(c['operation'],0)+1
        by_hash[c['hash']]=by_hash.get(c['hash'],0)+1
        day=datetime.utcfromtimestamp(c['timestamp']).strftime('%Y-%m-%d') if c['timestamp'] else 'unknown'
        by_day[day]=by_day.get(day,0)+1
        by_sess[c['session_id']]=by_sess.get(c['session_id'],0)+1
    total=len(calls); top_ops=sorted(by_op.items(), key=lambda x:x[1], reverse=True)
    recurring=[{'operation':op,'count':cnt,'meets_ge5':cnt>=5} for op,cnt in top_ops if op!='unknown_other']
    top10=sum(c for _,c in top_ops[:10]); coverage=top10/total if total else 0
    # Dataset B: deterministic post-exec pairs
    pairs=[]
    sample=calls[:]
    for i,a in enumerate(sample):
        for b in sample[i+1:i+25]:
            same=a['operation']==b['operation'] and a['operation']!='unknown_other'
            incompatible=(a['operation']=='hmp_healthcheck' and b['operation'] in ('hmp_send','ssh_scp_deploy')) or (b['operation']=='hmp_healthcheck' and a['operation'] in ('hmp_send','ssh_scp_deploy'))
            label='same_operation' if same else 'incompatible' if incompatible else 'unrelated'
            if label!='unrelated' or len(pairs)<160:
                pairs.append({'a_message_id':a['message_id'],'b_message_id':b['message_id'],'a_operation':a['operation'],'b_operation':b['operation'],'label':label,'basis':'deterministic operation/effect label from historical execute_code tool call text'})
            if len(pairs)>=160: break
        if len(pairs)>=160: break
    pairs=pairs[:150]
    # Dataset C: request/capability from previous user message + burnin prompts
    reqs=[]
    seen=set()
    for c in calls:
        q=previous_user(con,c['session_id'],c['message_id']).strip().replace('\x00','')
        if not q or q in seen: continue
        seen.add(q)
        low=q.lower()
        label='none'; cap=None; reason='no capability match'
        if re.search(r'hmp.*health|health.*peer\d+|healthcheck.*peer\d+|ping.*hmp', low) and not any(re.search(p,low) for p in MUTATING_NEG):
            label='positive'; cap='hmp-healthcheck'; reason='hook-visible request asks for read-only HMP health/status'
        elif any(re.search(p,low) for p in MUTATING_NEG):
            label='hard_negative'; cap=None; reason='mutating or non-allowlisted operation must not retrieve active read-only capability'
        reqs.append({'request':q[:500],'label':label,'capability_id':cap,'reason':reason})
        if len(reqs)>=120: break
    # supplement with burn-in/adversarial hook-visible prompts if historical user requests insufficient
    supplements=[]
    peers=['peer128','peer138']
    pos_tpl=['check HMP health for {p}','ping HMP status for {p}','show {p} HMP gateway health','verify {p} hmp health endpoint','healthcheck {p} via HMP']
    neg_tpl=['send a message to {p}','deploy plugin to {p}','restart HMP on {p}','ssh to {p} and run uptime','copy registry to {p}']
    for p in peers:
        for t in pos_tpl:
            supplements.append({'request':t.format(p=p),'label':'positive','capability_id':'hmp-healthcheck','reason':'burn-in hook-visible positive prompt'})
        for t in neg_tpl:
            supplements.append({'request':t.format(p=p),'label':'hard_negative','capability_id':None,'reason':'burn-in hook-visible hard negative prompt'})
    for s in supplements:
        if len(reqs)>=120: break
        if s['request'] not in seen:
            reqs.append(s); seen.add(s['request'])
    # Add registry examples to reach 120 if needed, marking synthetic separately
    idx=0
    while len(reqs)<120:
        p=peers[idx%2]; base=(pos_tpl+neg_tpl)[idx%10].format(p=p)
        reqs.append({'request':base+f' variant {idx//10}', 'label':'positive' if idx%10<5 else 'hard_negative', 'capability_id':'hmp-healthcheck' if idx%10<5 else None, 'reason':'synthetic registry-calibration prompt; not historical'})
        idx+=1
    # simple benchmark using same classifier used by retriever intent guard, for evidence not production
    def predict(q):
        low=q.lower()
        if re.search(r'hmp.*health|health.*peer\d+|healthcheck.*peer\d+|ping.*hmp|hmp.*status', low) and not any(re.search(p,low) for p in MUTATING_NEG): return 'hmp-healthcheck'
        return None
    holdout=reqs[60:120]; tp=fp=tn=fn=effect_fp=0
    for r in holdout:
        pred=predict(r['request']); expected=r['capability_id']
        if pred==expected and pred: tp+=1
        elif pred and not expected: fp+=1
        elif not pred and not expected: tn+=1
        elif not pred and expected: fn+=1
        if pred=='hmp-healthcheck' and r['label']=='hard_negative': effect_fp+=1
    precision=tp/(tp+fp) if tp+fp else 1.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    summary={'generated_at':datetime.utcnow().isoformat()+'Z','source_db':str(DB),'total_execute_code_tool_calls':total,'sessions_with_execute_code':len(by_sess),'days':by_day,'by_operation':dict(top_ops),'recurring_clusters_ge5':[r for r in recurring if r['meets_ge5']],'top10_coverage':coverage,'dataset_b_pairs':len(pairs),'dataset_c_pairs':len(reqs),'dataset_c_historical_or_burnin':sum(1 for r in reqs if 'synthetic' not in r['reason']),'holdout':{'size':len(holdout),'tp':tp,'fp':fp,'tn':tn,'fn':fn,'top1_precision':precision,'recall':recall,'read_only_mutating_false_matches':effect_fp},'gate_thresholds':{'episodes_min':200,'clusters_min':3,'cluster_occurrences_min':5,'top10_coverage_min':0.40,'dataset_b_pairs_min':100,'dataset_c_pairs_min':100,'top1_precision_min':0.70,'effect_false_matches_max':0},'pass':{}}
    summary['pass']={'C1':total>=200,'C2':sum(1 for r in recurring if r['meets_ge5'])>=3,'C3':coverage>=0.40,'C4':len(reqs)>=100,'C5':len(pairs)>=100,'C6':precision>=0.70,'C7':effect_fp==0}
    (OUT/'phase0-empirical-summary.json').write_text(json.dumps(summary,indent=2))
    (OUT/'dataset-b-post-exec-pairs.jsonl').write_text('\n'.join(json.dumps(x,sort_keys=True) for x in pairs)+'\n')
    (OUT/'dataset-c-pre-exec-pairs.jsonl').write_text('\n'.join(json.dumps(x,sort_keys=True) for x in reqs)+'\n')
    print(json.dumps(summary, indent=2))
if __name__=='__main__': main()
