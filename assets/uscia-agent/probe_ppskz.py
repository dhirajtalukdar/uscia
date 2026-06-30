import os, sys, asyncio
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

MATERIAL = 'SLOT-EWMS4-2443'
PLANT = '1710'

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')

    # A_ProductSupplyPlanning — get ALL field values for this material
    # PPSKZ (PP/DS Planning Procedure) OData name unknown — print everything with values
    print(f'=== A_ProductSupplyPlanning: {MATERIAL} / {PLANT} ===')
    r = await dsc.get(
        '/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductSupplyPlanning',
        params={'$filter': f"Product eq '{MATERIAL}' and Plant eq '{PLANT}'",
                '$top': '1', '$format': 'json'}
    )
    items = r.get('value') or r.get('results') or []
    if items:
        for k, v in items[0].items():
            if k != '__metadata':
                print(f'  {k}: {v!r}')
    else:
        print('  No records returned')

    # A_ProductWorkScheduling — also check for PPSKZ here
    print(f'\n=== A_ProductWorkScheduling: {MATERIAL} / {PLANT} ===')
    r2 = await dsc.get(
        '/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductWorkScheduling',
        params={'$filter': f"Product eq '{MATERIAL}' and Plant eq '{PLANT}'",
                '$top': '1', '$format': 'json'}
    )
    items2 = r2.get('value') or r2.get('results') or []
    if items2:
        for k, v in items2[0].items():
            if k != '__metadata':
                print(f'  {k}: {v!r}')
    else:
        print('  No records returned')

    # A_ProductPlant — also check
    print(f'\n=== A_ProductPlant: {MATERIAL} / {PLANT} ===')
    r3 = await dsc.get(
        '/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlant',
        params={'$filter': f"Product eq '{MATERIAL}' and Plant eq '{PLANT}'",
                '$top': '1', '$format': 'json'}
    )
    items3 = r3.get('value') or r3.get('results') or []
    if items3:
        for k, v in items3[0].items():
            if k not in ('__metadata',) and not isinstance(v, dict):
                print(f'  {k}: {v!r}')
    else:
        print('  No records returned')

asyncio.run(probe())
