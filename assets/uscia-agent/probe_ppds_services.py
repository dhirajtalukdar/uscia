import os, sys, asyncio
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

MATERIAL = 'SLOT-EWMS4-2443'
PLANT = '1710'

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')

    services = [
        # Most likely to have AdvancedPlanning / MTVFP
        ('PPDS_RES_SCHEDULE',      '/sap/opu/odata/sap/PPDS_RES_SCHEDULE',      '$metadata'),
        ('PMRP_RECEIPT_SERVICE',   '/sap/opu/odata/sap/PMRP_RECEIPT_SERVICE',   '$metadata'),
        ('PMRP_SUPPLYCHAIN_SERVICE','/sap/opu/odata/sap/PMRP_SUPPLYCHAIN_SERVICE','$metadata'),
        ('PPDS_MRP_COCKPIT_SRV',   '/sap/opu/odata/sap/PPDS_MRP_COCKPIT_SRV',  '$metadata'),
        ('PP_MRP_COCKPIT_SRV',     '/sap/opu/odata/sap/PP_MRP_COCKPIT_SRV',    '$metadata'),
        ('C_PLANNEDORDERS_CDS',    '/sap/opu/odata/sap/C_PLANNEDORDERS_CDS',    '$metadata'),
    ]

    for label, base, path in services:
        r = await dsc.get(f'{base}/{path}', params={})
        code = r.get('status_code', '200') if r.get('error') else '200'
        raw = str(r)
        has_ap = any(kw in raw for kw in ['AdvancedPlanning', 'MTVFP', 'AdvancedPlng', 'PPDSPlanning'])
        print(f'[{code}] {label} | AdvancedPlanning/MTVFP: {has_ap}')
        if str(code) == '200' and has_ap:
            # Show context around the field
            idx = max(raw.find('AdvancedPlanning'), raw.find('MTVFP'))
            print(f'  CONTEXT: ...{raw[max(0,idx-50):idx+80]}...')

    # Direct entity probes on services that returned 200
    print('\n--- Direct entity probes on PPDS_RES_SCHEDULE ---')
    for entity in ['MaterialPPDS', 'ProductPPDS', 'PPDSMaterial', 'PPDSProduct',
                   'ResourceSchedule', 'PPDSOrder', 'PPDSPlannedOrder']:
        r = await dsc.get(
            f'/sap/opu/odata/sap/PPDS_RES_SCHEDULE/{entity}',
            params={'$filter': f"Material eq '{MATERIAL}' and Plant eq '{PLANT}'",
                    '$top': '1', '$format': 'json'}
        )
        code = r.get('status_code', '200') if r.get('error') else '200'
        items = r.get('value') or r.get('results') or []
        fields = list(items[0].keys()) if items else []
        has_ap = any('dvanced' in f or 'MTVFP' in f or 'PPDS' in f for f in fields)
        print(f'  [{code}] {entity}' + (f' fields={fields[:10]}' if str(code)=='200' and items else ''))

asyncio.run(probe())
