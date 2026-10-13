"""Assemble supplied research evidence and figures without inventing scientific verdicts."""
import csv
import html
from pathlib import Path

from energy_analysis import profile
from ensemble_material import canonical, checked
from local_diagnostics import ids
from material import object_fields
from path_process import write_json
from trajectory import common_bounds, draw_structure, plot_setup, source_digest, write_trajectory


def text(value,name):
    if not isinstance(value,str) or not value.strip() or len(value)>20000:
        raise ValueError(name+' requires nonempty text up to 20000 characters')
    return value


def cell(value):
    value = html.escape(str(value))
    for char in ('\\', '`', '*', '_', '[', ']', '#', '|'):
        value = value.replace(char, '\\' + char)
    return value.replace('\n','<br>')


def research_review(value):
    """Validate a generic Research Review without turning it into a verdict.

    The review is a bounded index over the canonical research records.  Reports
    retain it for traceability, while the original Result/Artifact evidence
    remains the source for any chemical claim.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('research_review must be an object')
    required = ('schema_version', 'review_id', 'state_digest', 'review_digest',
                'status', 'review_status', 'source_refs', 'findings',
                'contradictions', 'uncertainties', 'limitations', 'follow_up')
    object_fields(value, required + ('scope', 'coverage', 'read_more', 'guidance',
                                     'trigger', 'availability', 'error'), 'research review')
    if value.get('schema_version') != 'research-review/1':
        raise ValueError('research_review schema required')
    for key in ('review_id', 'state_digest', 'review_digest'):
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or len(item) > 256 or not item):
            raise ValueError(f'research_review {key} must be bounded text or null')
    if value.get('review_id') is None or value.get('state_digest') is None:
        # Failed hydration is a valid lifecycle observation, but a report with
        # a usable Review must identify the state it indexed.
        if value.get('review_status') != 'failed':
            raise ValueError('research_review identifiers required')
    if value.get('review_digest') is not None:
        expected = canonical({key: item for key, item in value.items() if key != 'review_digest'})
        if value['review_digest'] != expected:
            raise ValueError('research_review digest mismatch')
    if not isinstance(value.get('status'), str) or not value['status']:
        raise ValueError('research_review status required')
    if value.get('review_status') not in {'current', 'pending', 'stale', 'running', 'failed'}:
        raise ValueError('research_review review_status invalid')
    for key in ('source_refs', 'findings', 'contradictions', 'uncertainties', 'limitations', 'follow_up'):
        rows = value.get(key)
        if not isinstance(rows, list) or len(rows) > 512:
            raise ValueError(f'research_review {key} must be a bounded list')
    if any(not isinstance(ref, str) or not ref.strip() or len(ref) > 512 for ref in value['source_refs']):
        raise ValueError('research_review source_refs must contain bounded references')
    return value


def build_report(spec,output):
    object_fields(spec,('schema_version','title','question','assessment','limitations','structures','evidence','energy_profile','trajectory','research_review'),'research report')
    if spec.get('schema_version')!='chemical-research-report-input/1':raise ValueError('research report schema required')
    for k in ('title','question','assessment'):text(spec.get(k),k)
    review = research_review(spec.get('research_review'))
    limitations=spec.get('limitations')
    if not isinstance(limitations,list) or len(limitations)>128:raise ValueError('explicit limitations list required')
    for item in limitations:text(item,'limitation')
    evidence=spec.get('evidence')
    if not isinstance(evidence,list) or not 1<=len(evidence)<=128:raise ValueError('1..128 evidence records required')
    evidence_ids=set();records=[]
    for row in evidence:
        object_fields(row,('id','label','result','source_sha256','artifact_id'),'report evidence')
        label=text(row.get('label'),'evidence label');ident=text(row.get('id'),'evidence id')
        if ident in evidence_ids:raise ValueError('unique evidence IDs required')
        evidence_ids.add(ident)
        result=row.get('result')
        if not isinstance(result,dict) or not isinstance(result.get('schema_version'),str):raise ValueError('versioned evidence result required')
        if source_digest(row.get('source_sha256'))!=canonical(result):raise ValueError('evidence canonical digest mismatch')
        records.append({**row,'label':label,'reported_status':result.get('status',result.get('verdict','not_recorded'))})
    structures=spec.get('structures',[])
    if not isinstance(structures,list) or len(structures)>12:raise ValueError('at most 12 named structures')
    materials=[]
    for row in structures:
        object_fields(row,('label','material','display_bonds'),'report structure');text(row.get('label'),'structure label')
        m=checked(row.get('material'))
        if m['coordinates'] is None or not 1<=len(m['ids'])<=128:raise ValueError('report structures require 1..128 coordinate atoms')
        bonds=row.get('display_bonds',[])
        if not isinstance(bonds,list) or len(bonds)>512:raise ValueError('bounded display bonds required')
        for pair in bonds:
            if len(ids(pair,m,'display bond',2))!=2:raise ValueError('display bond needs exactly two atoms')
        materials.append(m)
    energy=profile(spec['energy_profile']) if spec.get('energy_profile') is not None else None
    # Validate nested trajectory before creating output or figures.
    if spec.get('trajectory') is not None:
        from trajectory import normalize
        normalize(spec['trajectory'])
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    plt=plot_setup()
    files=[]
    if materials:
        fig=plt.figure(figsize=(5*min(len(materials),3),4*((len(materials)+2)//3)))
        try:
            bounds=common_bounds([m['coordinates'] for m in materials])
            for i,(row,m) in enumerate(zip(structures,materials)):
                ax=fig.add_subplot((len(materials)+2)//3,min(len(materials),3),i+1,projection='3d')
                draw_structure(ax,m,m['coordinates'],row.get('display_bonds',[]),bounds,row['label'])
            fig.tight_layout();fig.savefig(out/'structures.png',dpi=100);files.append('structures.png')
        finally:plt.close(fig)
    if energy:
        write_json(out/'energy.json',energy)
        with (out/'energy.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['state','quantity','relative_energy','unit','reference'])
            for row in energy['rows']:writer.writerow([row['id'],energy['quantity'],row['relative_energy'],energy['unit'],energy['reference']])
        fig,ax=plt.subplots(figsize=(7,4))
        try:
            for i,row in enumerate(energy['rows']):ax.hlines(row['relative_energy'],i-.3,i+.3,linewidth=2)
            ax.set_xticks(range(len(energy['rows'])),[r['id'] for r in energy['rows']],rotation=25)
            ax.set_ylabel(f"Relative {energy['quantity']} ({energy['unit']})")
            ax.set_title('Discrete states; reference: '+energy['reference']);fig.tight_layout()
            fig.savefig(out/'energy.svg');fig.savefig(out/'energy.png',dpi=120)
        finally:plt.close(fig)
        files.extend(['energy.json','energy.csv','energy.svg','energy.png'])
    trajectory=write_trajectory(spec['trajectory'],out/'trajectory') if spec.get('trajectory') is not None else None
    files.append('report.md')
    if trajectory: files.extend('trajectory/'+f for f in ['result.json', *trajectory['files']])
    report={'schema_version':'chemical-research-report-result/1','input_sha256':canonical(spec),
        'author_assessment':spec['assessment'],'question':spec['question'],'evidence':records,
        'structures':[{'label':row['label'],'material_sha256':m['sha256']} for row,m in zip(structures,materials)],
        'energy':energy,'trajectory':trajectory,'limitations':limitations,
        'scientific_validation':'not_assessed','files':files,
        'research_review':review,
        'scope':'Evidence assembly with supplied author interpretation; canonical digests bind included data, not independent scientific certification'}
    write_json(out/'result.json',report)
    lines=['# '+cell(spec['title']),'','## Research question','',cell(spec['question']),
           '','## Author assessment','',cell(spec['assessment']),
           '','This assessment is supplied by the report author. Report generation does not certify a transition state or mechanism.',
           '','## Evidence','', '| Evidence | Schema | Reported status | Canonical SHA-256 |',
           '| --- | --- | --- | --- |']
    for row in records:lines.append('| '+' | '.join(cell(v) for v in (row['label'],row['result']['schema_version'],row['reported_status'],row['source_sha256']))+' |')
    lines.extend(['','Full checks, partial failures and source references are retained in result.json.'])
    if review:
        lines.extend(['','## Research Review','',
                      f"Review: `{cell(review.get('review_id'))}`; state: `{cell(review.get('state_digest'))}`; status: `{cell(review.get('review_status'))}` ({cell(review.get('status'))})."])
        if review.get('source_refs'):
            lines.extend(['','Indexed sources: '+', '.join(f'`{cell(ref)}`' for ref in review['source_refs'][:64])+'.'])
        for label, key in (('Contradictions', 'contradictions'), ('Uncertainties', 'uncertainties')):
            rows = review.get(key, [])
            lines.extend(['', f'### {label}'])
            lines.extend(['- '+cell(row.get('summary') if isinstance(row, dict) else row) for row in rows[:32]] or ['- None recorded in this bounded review.'])
        lines.extend(['','The Research Review is a derived index of recorded research state. It does not certify transition-state validity, mechanism, or completion; inspect the cited Result and Artifact records before making those claims.'])
    if materials:lines.extend(['','## Supplied structures','','![Supplied structures](structures.png)','','Fixed camera and scale; lines, if present, are explicitly supplied display bonds.'])
    if energy:lines.extend(['','## Energy comparison','','![Discrete energy levels](energy.png)','',f"Quantity: {cell(energy['quantity'])}; unit: {cell(energy['unit'])}; reference: {cell(energy['reference'])}.",'','Conditions and source models are preserved in energy.json; these levels are not a continuous potential surface.'])
    else:lines.extend(['','## Energy comparison','','Comparable energy data were not supplied.'])
    if trajectory:lines.extend(['','## Trajectory evidence','','![Trajectory illustration](trajectory/trajectory.gif)','','![Coordinate and energy profile](trajectory/profile.png)','',f"Source status: {cell(trajectory['source_status'])}. Frame index is not time; an animation does not establish IRC completion or a TS."])
    lines.extend(['','## Limitations','']+['- '+cell(v) for v in limitations])
    if not limitations:lines.append('No author limitations were supplied; this does not mean the evidence is complete.')
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return report
