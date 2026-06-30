"""One-shot DSC service probe — run as cf task or locally with IBD_TESTING=0."""
import os, sys, asyncio
sys.path.insert(0, 'app')
os.environ.setdefault('IBD_TESTING', '0')
from s4hana_client import S4Client

SERVICES = [
    ("/sap/opu/odata/sap/API_MRP_MATERIALS_SRV_01/A_MRPMaterial",
     {"$filter": "Material eq 'MZ-FG-C200' and MRPArea eq '1010'", "$top": "1", "$format": "json"}),
    ("/sap/opu/odata/sap/PPH_MANAGE_PLANNED_ORDER_SRV/A_PlannedOrder",
     {"$top": "1", "$format": "json"}),
    ("/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlantProcurement",
     {"$filter": "Product eq 'MZ-FG-C200' and Plant eq '1010'", "$top": "1", "$format": "json"}),
    ("/sap/opu/odata4/sap/api_product/srvd_a2x/sap/product/0001/ProductPlantMRP",
     {"$filter": "Product eq 'MZ-FG-C200' and Plant eq '1010'", "$top": "1"}),
    ("/sap/opu/odata/sap/MM_MATERIAL_MASTER_SRV/to_MRPArea",
     {"$top": "1", "$format": "json"}),
    ("/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product",
     {"$filter": "Product eq 'MZ-FG-C200'", "$top": "1", "$format": "json"}),
]

async def probe():
    dsc = S4Client(destination_name='S4HANA_DSC')
    for path, params in SERVICES:
        r = await dsc.get(path, params=params)
        code = r.get('status_code', '200') if r.get('error') else '200'
        label = path.split('/')[-1]
        print(f"[{code}] {label}")
        if str(code) == '200':
            # Show field names if any records returned
            items = r.get('value') or r.get('results') or []
            if items and isinstance(items, list):
                print(f"      fields: {list(items[0].keys())[:12]}")

asyncio.run(probe())
