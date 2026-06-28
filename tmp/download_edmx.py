import urllib.request, os

specs = [
    {
        "name": "ce-planned-orders",
        "ord_id": "sap.s4:apiResource:CE_PLANNED_ORDERS_0001:v1",
        # CE_PLANNED_ORDERS_0001 not found in catalog; using PLANNEDORDER_0001 EDMX (same underlying spec)
        "url": "https://hcp-5d1d08df-8d03-4cca-a753-9aa274e3057d.s3.amazonaws.com/staging/1781249131-Planned_Order_-_EDMX?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=[REDACTED]%2F20260612%2Feu-central-1%2Fs3%2Faws4_request&X-Amz-Date=20260612T072531Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=41898c57298dfae2e849fdd0b28abd8bd3edbae3febea687c138c1293e4d8818"
    },
    {
        "name": "planned-independent-requirement",
        "ord_id": "sap.s4:apiResource:OP_API_PLND_INDEP_RQMT_SRV_0001:v1",
        "url": "https://hcp-5d1d08df-8d03-4cca-a753-9aa274e3057d.s3.amazonaws.com/staging/1781249131-Planned_Independent_Requirement_-_EDMX?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=[REDACTED]%2F20260612%2Feu-central-1%2Fs3%2Faws4_request&X-Amz-Date=20260612T072531Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=860fd34b19363c10ffc7708fb80da6ad64876ad637c7263b986d837d32579e5b"
    },
    {
        "name": "ppds-stock-level",
        "ord_id": "sap.s4:apiResource:OP_PPDSPRODTDSTLV_0001:v1",
        "url": "https://hcp-5d1d08df-8d03-4cca-a753-9aa274e3057d.s3.amazonaws.com/staging/1781249131-PPDS_Product_Time_Dependent_Stock_Level_-_EDMX?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=[REDACTED]%2F20260612%2Feu-central-1%2Fs3%2Faws4_request&X-Amz-Date=20260612T072531Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=020cf1342895e9d01813df766fce5c5af423a302e158551fd4ba0ada71e78b3c"
    },
    {
        "name": "ppds-flexible-constraints",
        "ord_id": "sap.s4:apiResource:OP_APIFLEXIBLECONSTRAINTS_0001:v1",
        "url": "https://hcp-5d1d08df-8d03-4cca-a753-9aa274e3057d.s3.amazonaws.com/staging/1781249131-Flexible_Constraint_for_PPDS_-_EDMX?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=[REDACTED]%2F20260612%2Feu-central-1%2Fs3%2Faws4_request&X-Amz-Date=20260612T072531Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=e0edb7026f1b0dfc53c5ccb5802c61092aa887a31644092cd4d305a6b7d12e87"
    },
    {
        "name": "advanced-atp-check",
        "ord_id": "sap.s4:apiResource:CE_APIAVAILTOPROMISECHECK_0001:v1",
        "url": "https://hcp-5d1d08df-8d03-4cca-a753-9aa274e3057d.s3.amazonaws.com/staging/1781249131-Advanced_ATP_Check_-_EDMX?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=[REDACTED]%2F20260612%2Feu-central-1%2Fs3%2Faws4_request&X-Amz-Date=20260612T072531Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=34e9b3c92edbf549da5873e197a1b45b9fa0aa5d0fca698ae67a671ff37645b3"
    },
    {
        "name": "material-planning-data",
        "ord_id": "sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1",
        "url": "https://hcp-5d1d08df-8d03-4cca-a753-9aa274e3057d.s3.amazonaws.com/staging/1781249131-Material_Planning_Data_-_Read_-_EDMX?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=[REDACTED]%2F20260612%2Feu-central-1%2Fs3%2Faws4_request&X-Amz-Date=20260612T072531Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=30d09d4efd5cdf717ff0ac9d8beb913cd0b99504309a6efec0e43da814cda5c7"
    },
]

out_dir = "specification/uscia-agent/api-specs"
os.makedirs(out_dir, exist_ok=True)

for spec in specs:
    dest = f"{out_dir}/{spec['name']}.edmx"
    print(f"Downloading {spec['name']}...", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(spec["url"], dest)
        size = os.path.getsize(dest)
        print(f"OK ({size:,} bytes) -> {dest}")
    except Exception as e:
        print(f"FAILED: {e}")
