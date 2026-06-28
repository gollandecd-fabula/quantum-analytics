import copy,json,re,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]; S=R/'schemas'; V=R/'tests/contracts/fixtures/b3-evidence-chain-vectors.json'; H=re.compile(r'^[a-f0-9]{64}$')
SIG={'RESULT_DEFINED_BY':('METRIC_SNAPSHOT','METRIC_DEFINITION'),'RESULT_CALCULATED_WITH':('METRIC_SNAPSHOT','CALCULATION_PROFILE'),'RESULT_USES_RESOLUTION':('METRIC_SNAPSHOT','RULE_RESOLUTION'),'RESOLUTION_SELECTS_RULE':('RULE_RESOLUTION','CONFIGURATION_RULE'),'PROFILE_SELECTS_RULE':('CALCULATION_PROFILE','CONFIGURATION_RULE'),'PROFILE_USES_ROUNDING':('CALCULATION_PROFILE','ROUNDING_POLICY'),'PROFILE_USES_SOURCE_AUTHORITY':('CALCULATION_PROFILE','SOURCE_AUTHORITY'),'RESULT_DERIVED_FROM_EVENT':('METRIC_SNAPSHOT','CANONICAL_EVENT'),'EVENT_NORMALIZED_FROM_RECORD':('CANONICAL_EVENT','SOURCE_RECORD'),'RECORD_READ_FROM_FILE':('SOURCE_RECORD','SOURCE_FILE'),'RESULT_USES_TRANSFORMATION':('METRIC_SNAPSHOT','TRANSFORMATION'),'RESULT_USES_PRODUCT_MASTER':('METRIC_SNAPSHOT','PRODUCT_MASTER'),'RESULT_HAS_FRESHNESS':('METRIC_SNAPSHOT','FRESHNESS_ASSESSMENT'),'RESULT_HAS_CONFIDENCE':('METRIC_SNAPSHOT','CONFIDENCE_ASSESSMENT'),'RESULT_RECONCILED_BY':('METRIC_SNAPSHOT','RECONCILIATION_RESULT'),'ARTIFACT_APPROVED_BY':(None,'APPROVAL'),'SNAPSHOT_SUPERSEDES':('METRIC_SNAPSHOT','METRIC_SNAPSHOT'),'SNAPSHOT_RESTATES':('METRIC_SNAPSHOT','METRIC_SNAPSHOT')}
def j(p): return json.loads(p.read_text())
def ref(x): return isinstance(x.get('version'),int) and not isinstance(x.get('version'),bool) and x['version']>0 and bool(H.fullmatch(str(x.get('content_hash','')))) and bool(x.get('id'))
def diagnose(g):
 n={x['node_id']:x for x in g.get('nodes',[])}
 if len(n)!=len(g.get('nodes',[])): return 'EVIDENCE_NODE_MISSING'
 if not isinstance(g.get('version'),int) or isinstance(g.get('version'),bool) or g['version']<1: return 'EVIDENCE_VERSION_INVALID'
 if not H.fullmatch(str(g.get('content_hash',''))): return 'EVIDENCE_HASH_MISMATCH'
 if not ref(g.get('root_metric_snapshot_ref',{})): return 'EVIDENCE_VERSION_INVALID' if g.get('root_metric_snapshot_ref',{}).get('version',0)<1 else 'EVIDENCE_HASH_MISMATCH'
 root=[x for x in n.values() if x['node_type']=='METRIC_SNAPSHOT' and x['artifact_ref']==g['root_metric_snapshot_ref']]
 if len(root)!=1:return 'EVIDENCE_NODE_MISSING'
 for x in n.values():
  if not ref(x.get('artifact_ref',{})):return 'EVIDENCE_VERSION_INVALID' if x.get('artifact_ref',{}).get('version',0)<1 else 'EVIDENCE_HASH_MISMATCH'
  if x.get('organization_id')!=g.get('organization_id'):return 'EVIDENCE_TENANT_MISMATCH'
  if x.get('mode')!=g.get('mode') or (g.get('mode')=='ACTUAL' and x.get('scenario_id') is not None) or (g.get('mode')=='SCENARIO' and x.get('scenario_id')!=g.get('scenario_id')):return 'EVIDENCE_MODE_CONTAMINATION'
 a={k:[] for k in n}; t={}
 for e in g.get('edges',[]):
  u,v,z=e.get('from_node_id'),e.get('to_node_id'),e.get('edge_type')
  if u not in n or v not in n:return 'EVIDENCE_NODE_MISSING'
  if z not in SIG:return 'EVIDENCE_EDGE_INVALID'
  p,q=SIG[z]
  if (p and n[u]['node_type']!=p) or n[v]['node_type']!=q:return 'EVIDENCE_EDGE_INVALID'
  a[u].append(v);t.setdefault((u,z),[]).append(v)
 seen=set();stack=set()
 def cyc(x):
  if x in stack:return True
  if x in seen:return False
  stack.add(x)
  if any(cyc(y) for y in a[x]):return True
  stack.remove(x);seen.add(x);return False
 if any(cyc(x) for x in n):return 'EVIDENCE_GRAPH_CYCLE'
 rid=root[0]['node_id']
 def targets(u,z,typ):return [v for v in t.get((u,z),[]) if n[v]['node_type']==typ]
 basics=[('RESULT_DEFINED_BY','METRIC_DEFINITION'),('RESULT_CALCULATED_WITH','CALCULATION_PROFILE'),('RESULT_USES_RESOLUTION','RULE_RESOLUTION'),('RESULT_USES_TRANSFORMATION','TRANSFORMATION'),('RESULT_DERIVED_FROM_EVENT','CANONICAL_EVENT'),('RESULT_HAS_FRESHNESS','FRESHNESS_ASSESSMENT'),('RESULT_HAS_CONFIDENCE','CONFIDENCE_ASSESSMENT')]
 if any(not targets(rid,z,typ) for z,typ in basics):return 'EVIDENCE_REQUIRED_PATH_MISSING'
 for p in targets(rid,'RESULT_CALCULATED_WITH','CALCULATION_PROFILE'):
  if not targets(p,'PROFILE_USES_ROUNDING','ROUNDING_POLICY') or not targets(p,'PROFILE_USES_SOURCE_AUTHORITY','SOURCE_AUTHORITY'):return 'EVIDENCE_REQUIRED_PATH_MISSING'
 for x in targets(rid,'RESULT_USES_RESOLUTION','RULE_RESOLUTION'):
  if not targets(x,'RESOLUTION_SELECTS_RULE','CONFIGURATION_RULE'):return 'EVIDENCE_REQUIRED_PATH_MISSING'
 for e in targets(rid,'RESULT_DERIVED_FROM_EVENT','CANONICAL_EVENT'):
  rec=targets(e,'EVENT_NORMALIZED_FROM_RECORD','SOURCE_RECORD')
  if not rec:return 'EVIDENCE_REQUIRED_PATH_MISSING'
  for r in rec:
   fs=targets(r,'RECORD_READ_FROM_FILE','SOURCE_FILE')
   if not fs:return 'EVIDENCE_REQUIRED_PATH_MISSING'
   for f in fs:
    m=n[f].get('metadata',{})
    if not H.fullmatch(str(m.get('retained_bytes_sha256',''))) or not m.get('storage_locator'):return 'EVIDENCE_SOURCE_FILE_UNAVAILABLE'
 return None
def mutate(base,m):
 g=copy.deepcopy(base)
 if 'remove_node'in m:
  x=m['remove_node'];g['nodes']=[n for n in g['nodes'] if n['node_id']!=x];g['edges']=[e for e in g['edges'] if x not in(e['from_node_id'],e['to_node_id'])]
 if 'remove_edge'in m:
  x=m['remove_edge'];g['edges']=[e for e in g['edges'] if not all(e.get(k)==v for k,v in x.items())]
 if 'add_edge'in m:g['edges'].append(m['add_edge'])
 if 'replace_edge'in m:
  x=m['replace_edge'];next(e for e in g['edges'] if e['from_node_id']==x['from_node_id'] and e['to_node_id']==x['to_node_id'] and e['edge_type']==x['edge_type'])['edge_type']=x['new_edge_type']
 if 'node_id'in m:
  n=next(n for n in g['nodes'] if n['node_id']==m['node_id']);n.update({k:v for k,v in m.items() if k!='node_id'})
 if 'root_reference_version'in m:g['root_metric_snapshot_ref']['version']=m['root_reference_version']
 if 'graph_content_hash'in m:g['content_hash']=m['graph_content_hash']
 return g
class B3(unittest.TestCase):
 def test_01_b1a_dependencies(self):
  for p in ['docs/finance/CONFIGURATION_RULE_CONTRACT.md','docs/finance/RULE_RESOLUTION_CONTRACT.md','docs/finance/CALCULATION_PROFILE_CONTRACT.md','schemas/metric-definition.schema.json','schemas/calculation-profile.schema.json','tests/test_b1a_financial_contracts.py','docs/evidence/STAGE_B_B1A_CONTRACT_EVIDENCE.yaml']:self.assertTrue((R/p).is_file(),p)
 def test_02_schemas_json_no_defaults(self):
  for x in ['metric-result.schema.json','evidence-chain.schema.json']:self.assertNotIn('"default"',(S/x).read_text());self.assertEqual(j(S/x)['$schema'],'https://json-schema.org/draft/2020-12/schema')
 def test_03_states_and_zero(self):
  c=set(j(S/'typed-value.schema.json')['properties']['state']['enum']);m=j(S/'metric-result.schema.json');self.assertEqual(set(m['$defs']['typedState']['enum']),c);self.assertNotIn('ZERO_VALID',c);self.assertNotEqual(m['allOf'][2]['then']['properties']['value'],{'type':'null'})
 def test_04_units_align(self):
  a=set(j(S/'metric-definition.schema.json')['properties']['unit']['enum']);b=set(j(S/'metric-result.schema.json')['properties']['unit']['enum']);b.discard(None);self.assertTrue(a<=b,a-b);self.assertIn('MONEY_PER_ITEM',b)
 def test_05_positive_refs(self):
  for x in ['metric-result.schema.json','evidence-chain.schema.json']:self.assertEqual(j(S/x)['$defs']['versionedRef']['properties']['version'],{'type':'integer','minimum':1})
 def test_06_fixture_schema_shape(self):
  g=j(V)['valid_graph'];s=j(S/'evidence-chain.schema.json');self.assertEqual(set(g),set(s['required']));self.assertTrue(all(set(n)==set(s['$defs']['node']['required']) for n in g['nodes']));self.assertTrue(all(set(e)==set(s['$defs']['edge']['required']) for e in g['edges']))
 def test_07_valid_graph(self):self.assertIsNone(diagnose(j(V)['valid_graph']))
 def test_08_invalid_vectors(self):
  d=j(V)
  for v in d['invalid_vectors']:self.assertEqual(diagnose(mutate(d['valid_graph'],v['mutation'])),v['expected_diagnostic'],v['id'])
 def test_09_mode_isolation(self):
  for x in ['metric-result.schema.json','evidence-chain.schema.json']:
   q=json.dumps(j(S/x));self.assertIn('ACTUAL',q);self.assertIn('SCENARIO',q);self.assertIn('scenario_id',q)
 def test_10_metric_contract(self):
  q=(R/'docs/evidence/METRIC_SNAPSHOT_CONTRACT.md').read_text()
  for x in ['Numeric zero is a valid payload of `VALID`','expense boundary','freshness','confidence','prior snapshot identifier','Actual and Scenario isolation','Aliases such as `latest`','MONEY_PER_ITEM']:self.assertIn(x,q)
 def test_11_evidence_contract(self):
  q=(R/'docs/evidence/EVIDENCE_CHAIN_CONTRACT.md').read_text()
  for x in ['SOURCE_RECORD -> RECORD_READ_FROM_FILE -> SOURCE_FILE','RULE_RESOLUTION -> RESOLUTION_SELECTS_RULE -> CONFIGURATION_RULE','Merely making each required node type reachable','Every node has a stable ID','The calculation subgraph must be acyclic','EVIDENCE_REQUIRED_PATH_MISSING','EVIDENCE_REPRODUCTION_FAILED']:self.assertIn(x,q)
if __name__=='__main__':unittest.main()
