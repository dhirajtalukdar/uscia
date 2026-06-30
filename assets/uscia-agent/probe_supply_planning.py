import os, sys, asyncio
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

MATERIAL = 'SLOT-EWMS4-2443'
PLANT = '1710'

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')

    # 1. A_ProductSupplyPlanning — contains AdvancedPlanning (MTVFP) if exposed
    print(f'--- Probing material={MATERIAL} plant={PLANT} ---')

    entities = [
        ('A_ProductSupplyPlanning',  f"Product eq '{MATERIAL}' and Plant eq '{PLANT}'"),
        ('A_ProductPlant',           f"Product eq '{MATERIAL}' and Plant eq '{PLANT}'"),
        ('A_ProductPlantMRPArea',    f"Product eq '{MATERIAL}' and Plant eq '{PLANT}' and MRPArea eq '{PLANT}'"),
    ]

    for entity, filt in entities:
        r = await dsc.get(
            f'/sap/opu/odata/sap/API_PRODUCT_SRV/{entity}',
            params={'$filter': filt, '$top': '1', '$format': 'json'}
        )
        code = r.get('status_code', '200') if r.get('error') else '200'
        items = r.get('value') or r.get('results') or []
        fields = list(items[0].keys()) if items else []
        data = items[0] if items else {}

        print(f'\n[{code}] {entity}')
        if str(code) == '200' and items:
            print(f'  All fields: {fields}')
            # PPDS-relevant fields specifically
            ppds_fields = {k: v for k, v in data.items()
                          if any(kw in k for kw in ['dvanced', 'MTVFP', 'MRP', 'Plng', 'Planning',
                                                     'Schedule', 'PPDS', 'Heuristic', 'Fence',
                                                     'Safety', 'Delivery', 'Procurement'])}
            print(f'  PPDS/MRP relevant: {ppds_fields}')
        elif str(code) == '200':
            print(f'  200 OK but 0 records returned for this material/plant')
        else:
            print(f'  error: {str(r.get("message",""))[:200]}')

    # 2. Navigate via A_Product -> to_Plant -> to_ProductSupplyPlanning
    nav_path = f"/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('{MATERIAL}')/to_Plant('{PLANT}')/to_ProductSupplyPlanning"
    r = await dsc.get(nav_path, params={'$format': 'json'})
    code = r.get('status_code', '200') if r.get('error') else '200'
    items = r.get('value') or r.get('results') or ([r] if not r.get('error') else [])
    data = items[0] if items else {}
    print(f'\n[{code}] navigation to_ProductSupplyPlanning')
    if str(code) == '200' and data:
        print(f'  All fields: {list(data.keys())}')
        ap = data.get('AdvancedPlanning')
        mtvfp = data.get('MTVFP')
        print(f'  AdvancedPlanning={ap}  MTVFP={mtvfp}')
    elif str(code) == '200':
        print(f'  200 OK but empty')
    else:
        print(f'  error: {str(r.get("message",""))[:200]}')

asyncio.run(probe())
