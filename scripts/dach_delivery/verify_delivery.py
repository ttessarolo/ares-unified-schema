#!/usr/bin/env python3
"""Offline contract and package checks; never connects to ARES/OpenSearch."""
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from jsonschema import Draft7Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs'
TENANTS=['JOYN','JOYN_AT','JOYN_CH']
EXPECTED={f'{metric}_{tenant}_{segment}_{window}' for metric in ['unique_viewers','views'] for tenant in TENANTS for segment in ['AVOD','SVOD'] for window in ['1d','2d','7d']}
ACTIVE={'active_distribution_tenants','active_distribution_models','active_access_rules','active_brand_codes'}
DATES={'broadcast_date_joyn','broadcast_date_joyn_at','broadcast_date_joyn_ch'}
checks=[]

def load(path):return json.loads((OUT/path).read_text())
def check(name,condition):
    assert condition,name
    checks.append(name)
def expect(v, value, valid, name):check(name,v.is_valid(value)==valid)
def changed(data,key,val):
    d=copy.deepcopy(data);d[key]=val;return d

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--skip-manifest',action='store_true');parser.add_argument('--write-receipt',action='store_true');args=parser.parse_args()
    content=load('schemas/content-loader.schema.json');counter=load('schemas/counters-loader.schema.json');output=load('contracts/content-output-contract.json');mapping=load('opensearch/dach-content.mapping.json')['mappings'];profiles=load('contracts/loader-profiles.json')
    validators=[]
    for name,s in [('content input',content),('counters',counter),('flat output',output)]:
        Draft7Validator.check_schema(s);checks.append(name+' Draft-07 valid');validators.append(Draft7Validator(s,format_checker=FormatChecker()))
    ci,cv,ov=validators
    expect(ci,{'id':'SYNTHETIC-001'},True,'ID-only delete accepted')
    for val in [{},{'id':''},{'id':'   '},{'id':123}]:expect(ci,val,False,'content invalid ID rejected '+str(val))
    expect(ci,load('contracts/synthetic-content.json'),True,'structured content fixture accepted')
    for typ in ['EPISODE','CLIP','MOVIE','SEASON','SERIES']:
        expect(ci,{'id':'SYNTHETIC-001','type':typ,'titles':[{'text':'Synthetic','type':'main','language':{'code':'deu','standard':'ISO'}}]},True,'kind accepted '+typ)
    expect(ci,{'id':'SYNTHETIC-001','type':'MOVIE','titles':'not an array'},False,'known source array type enforced')
    expect(ci,{'id':'SYNTHETIC-001','futureExtension':{'value':1}},True,'unselected future fields can be forwarded')
    expect(ci,{'id':'SYNTHETIC-001','type':'MOVIE','visibilities':[{'distributionTenant':'OTHER_SYNTHETIC_MARKET'}]},True,'full ingress can carry out-of-scope market data')
    check('36 exact DACH counter fields',set(counter['properties'])==EXPECTED|{'id'})
    check('complete counter snapshot required',set(counter['required'])==EXPECTED|{'id'})
    check('counter allowlist strict',counter['additionalProperties'] is False)
    fixture=load('contracts/synthetic-counters.json');field='views_JOYN_SVOD_1d'
    expect(cv,fixture,True,'complete counter fixture accepted')
    for val in [0,1,9007199254740991,None]:expect(cv,changed(fixture,field,val),True,'counter accepted '+str(val))
    for val in [-1,0.5,9007199254740992,'42',True,[],{}]:expect(cv,changed(fixture,field,val),False,'counter invalid value '+str(val))
    missing=copy.deepcopy(fixture);missing.pop(field);expect(cv,missing,False,'missing owned counter rejected')
    for key in ['title','fingerprint','visibilities','views_OTHER_SVOD_1d']:
        expect(cv,changed(fixture,key,1),False,'unowned counter input rejected '+key)
    sample={'id':'SYNTHETIC-001','fingerprint_super':'','productionYear':'2026',**{k:None for k in DATES},**{k:[] for k in ACTIVE}}
    expect(ov,sample,True,'flat current-state empty and explicit date resets accepted')
    expect(ov,changed(sample,'productionYear',2026),False,'source productionYear remains string')
    expect(ov,changed(sample,'broadcast_date_joyn','invalid-date'),False,'invalid output date rejected')
    expect(ov,changed(sample,'broadcast_date_joyn','2030-10-09T12:00:00Z'),True,'RFC3339 output date accepted')
    expect(ov,changed(sample,'titles_text',['Synthetic main title']),True,'singleton title remains array')
    expect(ov,changed(sample,'titles_text','Synthetic main title'),False,'scalar title rejected')
    for key in ['fingerprint','fingerprint_metadata','visibilities','views_JOYN_SVOD_1d','age_ratings_rating_system']:
        expect(ov,changed(sample,key,[]),False,'unowned Super output rejected '+key)
    expect(ov,changed(sample,'brand_names',['Synthetic Brand']),True,'conditional Brand name output declared')
    check('strict shared mapping',mapping['dynamic']=='strict')
    props=mapping['properties'];check('each output field mapped',set(output['properties'])<=set(props))
    check('only known shared fields',set(props)==set(output['properties'])|EXPECTED|{'fingerprint','fingerprint_metadata','lastARESLoaderModified'})
    check('no raw windows or obsolete date',not any(k=='visibilities' or k.startswith('visibilities_') or k=='broadcastDate' for k in props))
    check('cast and crew roles distinct',props['cast_role']['type']==props['crew_role']['type']=='keyword' and 'roles' not in props)
    check('source productionYear mapped keyword',props['productionYear']['type']=='keyword')
    check('counter long no coercion',all(props[k]['type']=='long' and props[k]['coerce'] is False for k in EXPECTED))
    check('date formats and nulls',all(props[k]['type']=='date' and props[k]['format']=='strict_date_optional_time' and 'null_value' not in props[k] for k in DATES))
    check('aggregate keyword values',all(props[k]['type']=='keyword' for k in ACTIVE))
    check('no nested index fields',all(v['type'] not in ['nested','object'] for v in props.values()))
    check('three profile tenants only',profiles['scope']['tenants']==TENANTS)
    cp=profiles['profiles']['counters'];up=profiles['profiles']['umas_content']
    check('counter update only',cp['candidate_token_actions']==['u'] and cp['create_on_missing_content'] is False)
    check('counter no pipeline Merge flat schedules',cp['flatJsonOutput'] is False and cp['pipeline']['active'] is False and cp['merge']['active'] is False and cp['schedules']==[])
    sched=up['scheduling']['schedules'][0]
    check('structured windows and flags',sched['keys']['root']=='visibilities[].timeslots' and all(sched[k] is True for k in ['applyCurrentState','skipPastEvents','excludeFromOutput']))
    check('active start/end no destroy',sched['events']['start']['active'] and sched['events']['end']['active'] and not sched['events']['destroy']['active'] and sched['destroyExpired'] is False)
    check('Include uses structural paths',all('=' not in p for p in up['selected_source_paths']))
    check('schedule dependencies retained',{'visibilities[].timeslots[].start','visibilities[].timeslots[].end','visibilities[].distributionTenant','visibilities[].type','visibilities[].requiredAccessRights','visibilities[].brandCodes'}<=set(up['selected_source_paths']))
    check('selector only used before rating projection','ageRatings[].ratingSystem' not in up['selected_source_paths'])
    check('language and market filters',set(up['filters'])=={'titles[language.code=deu][type=main]','genres[].names[language.code=deu]','keywords[].names[language.code=deu]','visibilities[distributionTenant=JOYN|JOYN_AT|JOYN_CH]','relevantAiringInfo[distributionTenant=JOYN|JOYN_AT|JOYN_CH]'})
    text=(ROOT/'scripts/dach_delivery/document.md').read_text()
    check('no non-DACH tenant names in document',all(x not in text for x in ['MEDIASET_IT','MEDIASET_ES']))
    check('eight referenced opening open points',len(re.findall(r'^- \*\*.*§',text,flags=re.M))==8)
    headings={m.group(1) for m in re.finditer(r'^#{2,3} (\d+(?:\.\d+)?) ',text,re.M)}
    check('all open point references exist',set(re.findall(r'§(\d+(?:\.\d+)?)',text.split('## 1 Scope')[0]))<=headings)
    dictionary=text.split('## 11 Complete indexed schema dictionary',1)[1]
    rows=re.findall(r'^\| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| (.+) \|$',dictionary,re.M)
    check('dictionary lists every mapped field exactly once',len(rows)==len(props) and {r[0] for r in rows}==set(props))
    def json_shape(schema):
        if 'anyOf' in schema:return '|'.join(json_shape(v) for v in schema['anyOf'])
        if schema.get('type')=='array':
            inner=json_shape(schema['items']);return ('('+inner+')' if '|' in inner else inner)+'[]'
        return 'datetime' if schema.get('format')=='date-time' else schema['type']
    expected_shapes={k:json_shape(v) for k,v in output['properties'].items()}
    expected_shapes.update({k:json_shape(v) for k,v in counter['properties'].items() if k!='id'})
    expected_shapes.update(fingerprint='string',fingerprint_metadata='string',lastARESLoaderModified='datetime')
    check('dictionary JSON shapes match both contracts',all(typ==expected_shapes[field] for field,typ,_,_ in rows))
    check('dictionary OpenSearch types match mapping',all(os==props[field]['type']+(' + keyword' if 'fields' in props[field] else '') for field,_,os,_ in rows))
    check('dictionary descriptions populated',all(len(meaning)>20 for _,_,_,meaning in rows))
    for x in ['schemas/content-loader.schema.json','schemas/counters-loader.schema.json','opensearch/dach-content.mapping.json','figures/ingestion-three-lanes.svg','figures/ingestion-three-lanes.png','ARES-DACH-Ingestion-Specification.docx','ARES-DACH-Ingestion-Specification.pdf']:
        check('deliverable present '+x,(OUT/x).stat().st_size>0)
    with ZipFile(OUT/'ARES-DACH-Ingestion-Specification.docx') as z:
        tree=ET.fromstring(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        check('one embedded document figure',len(tree.findall('.//w:drawing',ns))==1)
        doc_text=' '.join(node.text or '' for node in tree.findall('.//w:t',ns))
        check('authoring comments not rendered','<!--' not in doc_text)
        check('DOCX contains dictionary and every mapped name','11 Complete indexed schema dictionary' in doc_text and all(k in doc_text for k in props))
    if not args.skip_manifest:
        manifest=load('manifest.json')
        for ent in manifest['files']:
            p=ROOT/ent['path'];d=p.read_bytes();assert len(d)==ent['bytes'] and hashlib.sha256(d).hexdigest()==ent['sha256'],ent['path']
        checks.append('portable package manifest hashes')
    receipt={'result':'PASS','checks':len(checks),'counter_fields':len(EXPECTED),'shared_index_fields':len(props),'tenants':TENANTS,'check_names':checks,'limits':['Offline schema and cross-artifact checks only.','No OpenSearch mapping application, deployed Loader execution, pipeline/decorator/scheduler execution, API load test or realtime measurement.','The 36-field counter snapshot remains a producer proposal; metadata fields are out of scope.']}
    if args.write_receipt:(OUT/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='check_names'},indent=2))

if __name__=='__main__':main()
