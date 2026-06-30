import os, sys, asyncio, re
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client

MATERIAL = 'SLOT-EWMS4-2443'
PLANT = '1710'

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')

    services = [
        'PPDS_CAPA_UTIL_OBJ_SRV',
        'PPDS_MRP_COCKPIT_SRV',
        'PPDS_RES_SCHEDULE',
    ]

    for svc in services:
        print(f'\n{"="*60}')
        print(f'SERVICE: {svc}')
        print('='*60)

        # Get metadata
        r = await dsc.get(f'/sap/opu/odata/sap/{svc}/$metadata', params={})
        if r.get('error'):
            print(f'  METADATA ERROR [{r.get("status_code")}]: {str(r.get("message",""))[:200]}')
            continue

        raw = str(r)

        # Extract EntitySet names
        entity_sets = re.findall(r'EntitySet Name="([^"]+)"', raw)
        print(f'  EntitySets ({len(entity_sets)}): {entity_sets}')

        # Check for PP/DS-specific fields
        ppds_keywords = ['PPSKZ','APOKZ','PPDSPlanning','AdvancedPlanning',
                        'PP/DS','Heuristic','SCM_RRP','PlanningProc',
                        'ResourcePlan','CapacityPlan','OrderSchedul']
        found_kw = [kw for kw in ppds_keywords if kw.lower() in raw.lower()]
        if found_kw:
            print(f'  PP/DS keywords found: {found_kw}')

        # Extract all Property names with labels
        props = re.findall(r'Property Name="([^"]+)"[^/]*?sap:label="([^"]*)"', raw)
        print(f'  Total properties: {len(props)}')

        # Show all entity types and their properties
        entities = re.findall(r'EntityType Name="([^"]+)"', raw)
        print(f'  EntityTypes: {entities}')

        # For each entity, show properties
        for etype in entities[:5]:  # first 5 entities
            # Find properties between this EntityType and the next
            pattern = rf'EntityType Name="{etype}"(.*?)(?=EntityType Name=|AssociationType|EntityContainer)'
            match = re.search(pattern, raw, re.DOTALL)
            if match:
                block = match.group(1)
                eprops = re.findall(r'Property Name="([^"]+)"[^/]*?sap:label="([^"]*)"', block)
                print(f'\n  [{etype}] ({len(eprops)} props):')
                for pname, label in eprops[:30]:
                    print(f'    {pname:<50} {label}')

        # Try fetching actual data for PPDS_RES_SCHEDULE
        if svc == 'PPDS_RES_SCHEDULE':
            print(f'\n  --- Live data probes on {svc} ---')
            for entity in entity_sets[:5]:
                r2 = await dsc.get(
                    f'/sap/opu/odata/sap/{svc}/{entity}',
                    params={'$top': '1', '$format': 'json'}
                )
                code = r2.get('status_code', '200') if r2.get('error') else '200'
                items = r2.get('value') or r2.get('results') or []
                fields = list(items[0].keys()) if items else []
                print(f'  [{code}] {entity}: {fields[:10] if fields else "(empty)"}')

asyncio.run(probe())
