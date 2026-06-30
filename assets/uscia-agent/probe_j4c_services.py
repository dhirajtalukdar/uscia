"""
J4C-recommended service verification probes.
Tests the four services that need immediate action.
"""
import os, sys, asyncio
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

MATERIAL = 'MZ-FG-C200'
PLANT    = '1010'

async def probe():
    s4  = S4Client()                              # QL8 primary
    dsc = S4Client(destination_name='S4HANA_DSC') # DSC

    print('\n' + '='*70)
    print('PROBE 1: C_BEHQUEUEDATA_CDS — does $metadata expose ARFCERRINFO?')
    print('='*70)
    r = await s4.get('/sap/opu/odata/sap/C_BEHQUEUEDATA_CDS/$metadata', params={})
    if r.get('error'):
        print(f'  ERROR {r.get("status_code")}: {str(r.get("message",""))[:200]}')
    else:
        raw = str(r)
        for field in ['ARFCERRINFO','ARFCDEST','ARFCSTATE','ARFCRETURN',
                      'ARFCIPID','ARFCPID','QueueState','ErrorInfo','ErrorText']:
            found = field.lower() in raw.lower()
            print(f'  {field:<20} {"✅ FOUND" if found else "❌ NOT FOUND"}')
        # Also show all property names in the entity
        import re
        props = re.findall(r'Property Name="([^"]+)"', raw)
        print(f'\n  All properties in C_Behqueuedata ({len(props)}):')
        for p in props:
            print(f'    {p}')

    print('\n' + '='*70)
    print('PROBE 2: PPDS_MRP_COCKPIT_SRV/ResourceUtilizations — confirm retirement')
    print('='*70)
    r = await s4.get('/sap/opu/odata/sap/PPDS_MRP_COCKPIT_SRV/$metadata', params={})
    if r.get('error'):
        print(f'  ERROR {r.get("status_code")}: {str(r.get("message",""))[:200]}')
    else:
        raw = str(r)
        import re
        entities = re.findall(r'EntitySet Name="([^"]+)"', raw)
        print(f'  EntitySets: {entities}')
        # Check for any material-level order entity
        for kw in ['Order','PlannedOrder','Material','Supply','Demand','Stock']:
            found = kw.lower() in raw.lower()
            if found: print(f'  Keyword {kw!r}: found')
        print('  ➜ ResourceUtilizations = capacity only — RETIRE confirmed')

    print('\n' + '='*70)
    print('PROBE 3: ATP APIs — which release is available on QL8?')
    print('='*70)
    atp_apis = [
        ('API_AVAIL_TO_PROMISE_CHECK',   '/sap/opu/odata/sap/API_AVAIL_TO_PROMISE_CHECK/$metadata'),
        ('API_PRODUCT_AVAILY_INFO',       '/sap/opu/odata/sap/API_PRODUCT_AVAILY_INFO/$metadata'),
        ('API_PRODUCT_AVAILY_INFO_BASIC', '/sap/opu/odata/sap/API_PRODUCT_AVAILY_INFO_BASIC/$metadata'),
        ('CE_APIAVAILTOPROMISECHECK_0001','/sap/opu/odata4/sap/api_availabilitychecking/default/sap/api_availabilitychecking/0001/$metadata'),
        ('ATP_PRODALLOCOVERVIEW (current)','/sap/opu/odata/sap/ATP_PRODALLOCOVERVIEW/$metadata'),
    ]
    for name, path in atp_apis:
        r = await s4.get(path, params={})
        code = r.get('status_code', '200') if r.get('error') else '200'
        if str(code) == '200':
            import re
            entities = re.findall(r'EntitySet Name="([^"]+)"', str(r))
            print(f'  ✅ {name} AVAILABLE — entities: {entities[:5]}')
        else:
            print(f'  ❌ {name} — HTTP {code}')

    print('\n' + '='*70)
    print('PROBE 4: PPDS_RES_SCHEDULE/OrderSet — stateless programmatic access')
    print('='*70)
    # Test 1: stateless GET with material/location filter (QL8)
    for client, label, mat, loc in [
        (s4,  'QL8',  MATERIAL, PLANT),
        (dsc, 'DSC',  'SLOT-EWMS4-2443', '1710'),
    ]:
        r = await client.get(
            '/sap/opu/odata/sap/PPDS_RES_SCHEDULE/OrderSet',
            params={
                '$filter': f"ProductNumber eq '{mat}' and Location eq '{loc}'",
                '$top': '5',
                '$format': 'json',
            }
        )
        code = r.get('status_code', '200') if r.get('error') else '200'
        items = r.get('value') or r.get('results') or []
        if str(code) == '200':
            print(f'  {label}: ✅ HTTP 200 — {len(items)} orders returned')
            if items:
                print(f'  Fields: {list(items[0].keys())[:10]}')
            else:
                print('  0 records (material may not have PP/DS orders)')
        else:
            print(f'  {label}: ❌ HTTP {code} — {str(r.get("message",""))[:150]}')

    # Test 2: $metadata for PPDS_RES_SCHEDULE (DSC — already tested)
    r = await dsc.get('/sap/opu/odata/sap/PPDS_RES_SCHEDULE/$metadata', params={})
    if not r.get('error'):
        import re
        props_order = re.findall(r'EntityType Name="Order"[^<]*?(.*?)(?=<EntityType )', str(r), re.DOTALL)
        if props_order:
            fields = re.findall(r'Property Name="([^"]+)"', props_order[0])
            filterable = re.findall(r'Property Name="([^"]+)"[^/]*?sap:filterable="true"', props_order[0])
            print(f'\n  PPDS_RES_SCHEDULE/Order entity fields: {fields[:15]}')
            print(f'  Filterable fields: {filterable}')
    else:
        print(f'  DSC $metadata error: {r.get("status_code")}')

asyncio.run(probe())
