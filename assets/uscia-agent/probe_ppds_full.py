import os, sys, asyncio, re
sys.path.insert(0, 'app')
os.environ['IBD_TESTING'] = '0'
from s4hana_client import S4Client
import httpx

MATERIAL = 'SLOT-EWMS4-2443'
PLANT = '1710'

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')
    dest = await dsc.destination()

    # These RAP services reject $format — need raw HTTP without injected params
    client_kwargs, extra = await dsc._client_kwargs(dest)
    auth = dsc._http_auth(dest)
    headers = {'Accept': 'application/xml'}
    headers.update(extra)

    services = [
        'PPDS_CAPA_UTIL_OBJ_SRV',
        'PPDS_MRP_COCKPIT_SRV',
        'PPDS_RES_SCHEDULE',
    ]

    for svc in services:
        print(f'\n{"="*60}')
        print(f'SERVICE: {svc}')
        print('='*60)

        url = f'{dest.url}/sap/opu/odata/sap/{svc}/$metadata'
        if dest.sap_client:
            url += f'?sap-client={dest.sap_client}'

        try:
            async with httpx.AsyncClient(**client_kwargs) as http:
                r = await http.get(url, auth=auth, headers=headers, timeout=20)
            code = r.status_code
            print(f'  HTTP {code}')
            if code == 200:
                raw = r.text
                # Extract EntitySet names
                entity_sets = re.findall(r'EntitySet Name="([^"]+)"', raw)
                entity_types = re.findall(r'EntityType Name="([^"]+)"', raw)
                print(f'  EntityTypes ({len(entity_types)}): {entity_types}')
                print(f'  EntitySets  ({len(entity_sets)}): {entity_sets}')

                # Check for PP/DS-specific keywords
                kws = ['PPSKZ','APOKZ','AdvancedPlanning','PPDSPlanning',
                       'Heuristic','SCM_RRP','PlanningProc','Advanced',
                       'PP/DS','PPDSMaterial','PPDSOrder']
                found = [k for k in kws if k.lower() in raw.lower()]
                print(f'  PP/DS keywords: {found if found else "NONE"}')

                # Show all properties per entity type
                for etype in entity_types:
                    pattern = rf'EntityType Name="{etype}"(.*?)(?=<EntityType |<Association |<EntityContainer )'
                    match = re.search(pattern, raw, re.DOTALL)
                    if match:
                        block = match.group(1)
                        props = re.findall(r'Property Name="([^"]+)"[^/]*?sap:label="([^"]*)"', block)
                        if props:
                            print(f'\n  [{etype}] ({len(props)} props):')
                            for pname, label in props:
                                # Highlight PP/DS relevant ones
                                flag = ' ***' if any(k in (pname+label).upper() for k in
                                    ['PPDS','ADVANCED','HEURIST','PPSKZ','APOKZ','SCM_RRP',
                                     'PLANNING PROC','INDICATOR','APO']) else ''
                                print(f'    {pname:<50} {label}{flag}')
            else:
                print(f'  Error: {r.text[:300]}')
        except Exception as e:
            print(f'  Exception: {e}')

asyncio.run(probe())
