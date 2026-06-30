import os, sys, asyncio
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

ZAPI_SERVICES = [
    'ZAPI_PRODUCT_SRV',
    'ZAPI_MRP_MATERIALS_SRV_01',
    'ZAPI_MRP_MATERIALS_SRV',
]

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')

    for svc in ZAPI_SERVICES:
        r = await dsc.get(f'/sap/opu/odata/sap/{svc}/$metadata', params={})
        if r.get('error'):
            print(f'[{r.get("status_code")}] {svc} - NOT available')
            continue

        raw = str(r)
        # Extract entity set names from raw metadata string
        import re
        entity_sets = re.findall(r"Name=['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", raw)
        has_ap = 'AdvancedPlanning' in raw or 'MTVFP' in raw
        print(f'[200] {svc}')
        print(f'  AdvancedPlanning/MTVFP in metadata: {has_ap}')
        # Show unique entity names (filter noise)
        unique = sorted(set(e for e in entity_sets if not e.startswith('Edm')))[:20]
        print(f'  Entities: {unique}')

    # Direct entity probes on ZAPI_PRODUCT_SRV
    for entity in ['A_ProductPlant', 'A_ProductPlantMRP', 'A_ProductPlantMrp',
                   'A_ProductMRPArea', 'ProductMRPPlant', 'A_PlantMRP']:
        r = await dsc.get(
            f'/sap/opu/odata/sap/ZAPI_PRODUCT_SRV/{entity}',
            params={'$filter': "Product eq 'MZ-FG-C200' and Plant eq '1010'",
                    '$top': '1', '$format': 'json'}
        )
        code = r.get('status_code', '200') if r.get('error') else '200'
        fields = list((r.get('value') or r.get('results') or [{}])[0].keys())[:12] if not r.get('error') else []
        has_ap = any('dvanced' in f or 'MTVFP' in f or 'MRP' in f for f in fields)
        print(f'  [{code}] {entity}' + (f' fields={fields}' if str(code) == '200' else ''))

asyncio.run(probe())
