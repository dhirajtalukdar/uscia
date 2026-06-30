import os, sys, asyncio, re
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

MATERIAL = 'SLOT-EWMS4-2443'
PLANT = '1710'

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')

    # Read full metadata of MM_MATERIAL_PRODUCT_API
    print('=== MM_MATERIAL_PRODUCT_API $metadata ===')
    r = await dsc.get(
        '/sap/opu/odata/sap/MM_MATERIAL_PRODUCT_API/$metadata',
        params={}
    )
    if r.get('error'):
        print(f'ERROR [{r.get("status_code")}]: {str(r.get("message",""))[:300]}')
        return

    raw = str(r)

    # Extract all EntityType names and their properties
    # Pattern: EntityType Name="..." then Property Name="..." sap:label="..."
    entity_blocks = re.findall(
        r'EntityType Name="([^"]+)"(.*?)(?=EntityType Name=|AssociationType|$)',
        raw, re.DOTALL
    )

    for ename, block in entity_blocks:
        props = re.findall(
            r'Property Name="([^"]+)"[^/]*?(?:sap:label="([^"]*)")?[^/]*?(?:sap:quickinfo="([^"]*)")?',
            block
        )
        print(f'\n--- EntityType: {ename} ---')
        for pname, label, quickinfo in props:
            desc = quickinfo or label or ''
            print(f'  {pname:<50} {desc}')

    # Also list all EntitySet names
    sets = re.findall(r'EntitySet Name="([^"]+)"', raw)
    print(f'\n=== EntitySets ({len(sets)}) ===')
    for s in sets:
        print(f'  {s}')

asyncio.run(probe())
