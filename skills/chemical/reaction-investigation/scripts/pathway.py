"""Audit explicit pathway hypotheses; research Node edges are not chemical steps."""
from collections import Counter

from analysis_material import validate_material
from check_common import content_digest
from conformers import state_comparison
from energy_common import canonical, fields, integer, label, schema, source
from irc_check import irc_check
from kinetic_network import side
from mode_check import mode_check


def inventory(stoich, materials):
    result={};charge=0
    for key,count in stoich.items():
        m=materials[key]; value=m['value']
        if type(value.get('charge')) is not int: raise ValueError('pathway species requires declared charge')
        charge+=count*value['charge']
        for instance in range(count):
            for atom in m['atoms']:
                result[(key,instance,atom['atom_id'])]=(atom['element'],atom.get('isotope'))
    if len(result)>1024: raise ValueError('pathway state exceeds 1024 atoms')
    return result,charge


def validate_step_evidence(payload, step, materials):
    if payload is None: return {'status':'missing','scientific_verdict':'not_assessed'}
    fields(payload,('saddle_material','saddle_evidence','mode_coordinates','paths'),'step validation')
    if len(step['reactants'])!=1 or len(step['products'])!=1 or list(step['reactants'].values())!=[1] or list(step['products'].values())!=[1]:
        return {'status':'not_assessed','reason':'IRC validation requires single complete endpoint materials; associate separate fragments explicitly first'}
    saddle=validate_material(payload['saddle_material'],content_digest(payload['saddle_material']))
    targets=[materials[next(iter(step[k]))] for k in ('reactants','products')]
    mode=mode_check(saddle,payload['saddle_evidence'],payload['mode_coordinates'])
    path=irc_check(saddle,payload['saddle_evidence'],payload['paths'],targets)
    verdicts=[mode['verdict'],path['verdict']]
    return {'status':'pass' if all(v=='pass' for v in verdicts) else 'fail' if 'fail' in verdicts else 'inconclusive',
            'mode':mode,'irc':path,'scope':'Recomputed stationary/mode/IRC checks for these exact endpoint materials; not mechanism uniqueness'}


def pathway(spec):
    schema(spec,'chemical-pathway-input/1',('species','hypotheses','steps','routes','reactants','products','budget','unexplored'))
    species=spec.get('species'); hypotheses=spec.get('hypotheses'); steps=spec.get('steps'); routes=spec.get('routes')
    if not isinstance(species,dict) or not 1<=len(species)<=128: raise ValueError('1..128 pathway species required')
    materials={}
    for key,item in species.items():
        label(key,'species id');fields(item,('material','origin'),'species')
        origin=fields(item.get('origin'),('kind','source_sha256','hypothesis_id'),'origin')
        if origin.get('kind') not in ('provided','hypothesis','calculated'): raise ValueError('species origin must be explicit')
        source(origin.get('source_sha256'));m=item['material'];materials[key]=validate_material(m,content_digest(m))
        if not materials[key]['atoms']: raise ValueError('unresolved structure cannot support a pathway inventory')
    if not isinstance(hypotheses,dict) or not 1<=len(hypotheses)<=64: raise ValueError('1..64 hypotheses required')
    for key,hypothesis in hypotheses.items():
        label(key,'hypothesis id');fields(hypothesis,('statement','falsifier','source_sha256'),'hypothesis')
        label(hypothesis.get('statement'),'hypothesis statement');label(hypothesis.get('falsifier'),'falsifier');source(hypothesis.get('source_sha256'))
    for item in species.values():
        if item['origin']['kind']=='hypothesis' and item['origin'].get('hypothesis_id') not in hypotheses: raise ValueError('guessed species must preserve its hypothesis origin')
    budget=fields(spec.get('budget'),('max_jobs','max_candidates'),'budget')
    integer(budget.get('max_jobs'),'max_jobs',10000);integer(budget.get('max_candidates'),'max_candidates',10000)
    unexplored=spec.get('unexplored')
    if not isinstance(unexplored,list) or any(not isinstance(v,str) or not v.strip() for v in unexplored): raise ValueError('explicit unexplored questions required (possibly empty)')
    initial=side(spec.get('reactants'),species);target=spec.get('products')
    endpoint_balance=None
    if target is not None:
        side(target,species);a,qa=inventory(initial,materials);b,qb=inventory(target,materials)
        endpoint_balance=Counter(a.values())==Counter(b.values()) and qa==qb
    if not isinstance(steps,list) or len(steps)>256 or not isinstance(routes,dict) or len(routes)>64: raise ValueError('bounded steps and named routes required')
    reports={};indexed={}
    for step in steps:
        fields(step,('id','hypothesis_id','kind','reactants','products','mapping','observations','validation'),'step')
        ident=label(step.get('id'),'step id')
        if ident in indexed: raise ValueError('duplicate step id')
        if step.get('hypothesis_id') not in hypotheses: raise ValueError('step needs known hypothesis')
        if step.get('kind') not in ('elementary','unresolved','crossing'): raise ValueError('step kind required')
        left=side(step.get('reactants'),species);right=side(step.get('products'),species)
        a,qa=inventory(left,materials);b,qb=inventory(right,materials)
        balanced=Counter(a.values())==Counter(b.values()) and qa==qb
        mapping=step.get('mapping');map_status='missing';pairs=[]
        if mapping is not None:
            if not isinstance(mapping,list) or len(mapping)>1024: raise ValueError('bounded atom mapping required')
            seen_a=set();seen_b=set()
            for pair in mapping:
                if not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(v,list) or len(v)!=3 for v in pair): raise ValueError('mapping pair needs [species, zero-based instance, atom_id] on both sides')
                x,y=map(tuple,pair)
                if type(x[1]) is not int or type(y[1]) is not int or x not in a or y not in b or x in seen_a or y in seen_b: raise ValueError('mapping endpoints must be unique inventory atoms')
                seen_a.add(x);seen_b.add(y);pairs.append(a[x]==b[y])
            map_status='pass' if set(a)==seen_a and set(b)==seen_b and all(pairs) else 'fail'
        observations=step.get('observations',[])
        if not isinstance(observations,list) or len(observations)>256: raise ValueError('bounded observations required')
        for obs in observations:
            fields(obs,('source_sha256','interpretation','note'),'observation');source(obs.get('source_sha256'));label(obs.get('note'),'observation note')
            if obs.get('interpretation') not in ('supports','conflicts','unresolved'): raise ValueError('observation interpretation required')
        states=[m['value'] for k,m in materials.items() if k in set(left)|set(right)]
        known=all(type(m.get('multiplicity')) is int and m.get('electronic_state',{}).get('kind')!='unspecified' for m in states)
        # Fragment spin sums are deliberately not treated as total surface spin.
        state='not_assessed_fragment_coupling'
        if len(left)==len(right)==1 and list(left.values())==list(right.values())==[1]:
            state=state_comparison(materials[next(iter(left))]['value'],materials[next(iter(right))]['value'])['status']
        elif not known: state='incomplete_declarations'
        validation=validate_step_evidence(step.get('validation'),step,materials) if step['kind']=='elementary' else {'status':'not_assessed','reason':'requires specialized crossing evidence or elementary-step resolution'}
        conflict=not balanced or map_status=='fail' or any(o['interpretation']=='conflicts' for o in observations) or validation['status']=='fail'
        supported=balanced and map_status=='pass' and state=='compatible_declarations' and validation['status']=='pass'
        reports[ident]={'id':ident,'status':'conflicted' if conflict else 'supported_within_scope' if supported else 'incomplete',
            'balanced':balanced,'mapping':map_status,'state_continuity':state,'validation':validation,'observations':observations,
            'hypothesis_id':step['hypothesis_id']};indexed[ident]=step
    summaries=[]
    for name,route in routes.items():
        label(name,'route id')
        if not isinstance(route,list) or not 1<=len(route)<=256 or any(not isinstance(k,str) for k in route): raise ValueError('route requires ordered step IDs')
        current=initial;gaps=[]
        for ordinal,key in enumerate(route):
            if key not in indexed:
                gaps.append({'position':ordinal,'reason':'missing_step','step':key});current=None;continue
            if current!=indexed[key]['reactants']: gaps.append({'position':ordinal,'reason':'shared_intermediate_or_spectator_mismatch'})
            current=indexed[key]['products']
        if target is None: gaps.append({'reason':'product_target_unspecified'})
        elif current!=target:gaps.append({'reason':'route_does_not_reach_target'})
        complete=not gaps and all(reports[k]['status']=='supported_within_scope' for k in route)
        summaries.append({'id':name,'steps':route,'gaps':gaps,'status':'supported_within_scope' if complete else 'incomplete'})
    return {'schema_version':'chemical-pathway-result/1','request_sha256':canonical(spec),
        'status':'supported_within_scope' if summaries and all(r['status']=='supported_within_scope' for r in summaries) else 'incomplete',
        'endpoint_balance':endpoint_balance,'hypotheses':hypotheses,'species_origins':{k:v['origin'] for k,v in species.items()},'steps':list(reports.values()),
        'routes':summaries,'budget':budget,'unexplored':unexplored,
        'scope':'Audit of supplied pathways and recomputed optional classical step evidence; no automated exhaustive mechanism discovery, kinetic selection, excited-state or crossing certification.'}
