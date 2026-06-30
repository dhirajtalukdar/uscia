import os, sys, asyncio
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')

    # A_ProductSupplyPlanning — the PP/DS entity (navigation from A_ProductPlant)
    # Try direct entity set access first
    entities = [
        'A_ProductSupplyPlanning',
        'A_ProductPlantSupplyPlanning',
        'A_ProductPlant',
        'A_ProductPlantMRPArea',
    ]
    for entity in entities:
        r = await dsc.get(
            f'/sap/opu/odata/sap/API_PRODUCT_SRV/{entity}',
            params={'$filter': "Product eq 'MZ-FG-C200' and Plant eq '1010'",
                    '$top': '1', '$format': 'json'}
        )
        code = r.get('status_code', '200') if r.get('error') else '200'
        items = r.get('value') or r.get('results') or []
        fields = list(items[0].keys()) if items else []
        has_ap = any('dvanced' in f or 'MTVFP' in f or 'Supply' in f for f in fields)
        print(f'[{code}] {entity}')
        if str(code) == '200':
            print(f'  fields: {fields}')
            if has_ap:
                print(f'  *** AdvancedPlanning/PP/DS field found ***')
        else:
            print(f'  error: {str(r.get("message",""))[:150]}')

    # Also try navigation from A_Product to_ProductSupplyPlanning
    r = await dsc.get(
        "/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('MZ-FG-C200')/to_Plant('1010')/to_ProductSupplyPlanning",
        params={'$format': 'json'}
    )
    code = r.get('status_code', '200') if r.get('error') else '200'
    items = r.get('value') or r.get('results') or [r] if not r.get('error') else []
    fields = list(items[0].keys()) if items else []
    print(f'[{code}] navigation: A_Product->to_Plant->to_ProductSupplyPlanning')
    if str(code) == '200':
        print(f'  fields: {fields}')
        if any('dvanced' in f for f in fields):
            print(f'  *** AdvancedPlanning FOUND via navigation ***')

asyncio.run(probe())
