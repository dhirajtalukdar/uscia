import os
import logging
import json
import xml.etree.ElementTree as ET
import re
from dotenv import load_dotenv
import pyodata
import pyodata.v2.service
import requests
from requests.adapters import HTTPAdapter

load_dotenv()

logger = logging.getLogger("s4-mcp-server")
DEBUG = os.getenv("S4_DEBUG", "false").lower() == "true"


def _log(msg):
    if DEBUG:
        print(f"[ODATA] {msg}")


class _CCProxyAdapter(HTTPAdapter):
    """HTTPAdapter that injects Cloud Connector proxy auth headers."""

    def __init__(self, btp, location_id=None, **kwargs):
        self._btp = btp
        self._location_id = location_id
        super().__init__(**kwargs)

    def proxy_headers(self, proxy):
        headers = super().proxy_headers(proxy)
        headers["Proxy-Authorization"] = f"Bearer {self._btp.get_connectivity_token()}"
        if self._location_id:
            headers["SAP-Connectivity-SCC-Location_ID"] = self._location_id
        return headers

    def send(self, request, **kwargs):
        token = self._btp.get_connectivity_token()
        request.headers["Proxy-Authorization"] = f"Bearer {token}"
        if self._location_id:
            request.headers["SAP-Connectivity-SCC-Location_ID"] = self._location_id
        self.proxy_manager.clear()
        return super().send(request, **kwargs)


class S4ODataClient:
    """OData client for SAP S/4HANA connections.

    Supports direct basic auth or BTP Destination (Cloud Connector).
    """

    def __init__(self):
        self._btp = None
        self._destination_mode = False
        self._location_id = None
        self._proxy_url = None
        self.f4_entityset_cache = {}
        self.session = None

        destination_name = os.getenv("S4_ODATA_DESTINATION")
        if destination_name:
            self._init_destination_mode(destination_name)
        else:
            self._init_direct_mode()

    def _init_direct_mode(self):
        self.sap_host = os.getenv("S4_ODATA_HOST")
        self.sap_user = os.getenv("S4_ODATA_USER")
        self.sap_password = os.getenv("S4_ODATA_PASSWORD")
        self.sap_client = os.getenv("S4_ODATA_CLIENT")

        if not all([self.sap_host, self.sap_user, self.sap_password, self.sap_client]):
            print("Warning: S4 OData connection details are missing in environment variables.")

        if self.sap_host:
            self.base_url = f"https://{self.sap_host}/sap/opu/odata/sap"
        else:
            self.base_url = None

        self._initialize_session()

    def _init_destination_mode(self, destination_name):
        from clients.btp_service import BtpServiceConfig
        self._btp = BtpServiceConfig()
        dest = self._btp.get_http_destination(destination_name)
        proxy = self._btp.get_http_proxy()

        dest_url = dest["url"].rstrip("/")
        self.base_url = f"{dest_url}/sap/opu/odata/sap"

        self.sap_user = dest.get("user") or os.getenv("S4_ODATA_USER")
        self.sap_password = dest.get("password") or os.getenv("S4_ODATA_PASSWORD")
        self.sap_client = dest.get("sap_client") or os.getenv("S4_ODATA_CLIENT")
        self.sap_host = dest_url

        self._destination_mode = True
        self._location_id = dest.get("location_id")
        self._proxy_url = f"http://{proxy['proxy_host']}:{proxy['proxy_port']}"

        _log(f"Destination mode: url={dest_url}, proxy={self._proxy_url}, "
             f"location_id={self._location_id}")
        self._initialize_session()

    def _initialize_session(self):
        if self.base_url and not self.session:
            self.session = requests.Session()
            if self.sap_user and self.sap_password:
                self.session.auth = (self.sap_user, self.sap_password)
            if self.sap_client:
                self.session.params = {'sap-client': self.sap_client}
            self.session.verify = False
            requests.urllib3.disable_warnings(
                requests.urllib3.exceptions.InsecureRequestWarning)

            if self._destination_mode:
                adapter = _CCProxyAdapter(self._btp, self._location_id)
                self.session.mount("http://", adapter)
                self.session.mount("https://", adapter)
                self.session.proxies = {
                    "http": self._proxy_url,
                    "https": self._proxy_url,
                }
                print(f"Initialized OData session via BTP destination (proxy: {self._proxy_url})")
            else:
                print("Initialized OData session with basic authentication")

    def get_client_for_service(self, service_name: str):
        """Returns a pyodata client instance for a specific OData service."""
        if not self.base_url:
            raise ValueError("SAP connection details are missing in environment variables.")

        service_url = f"{self.base_url}/{service_name}/"

        try:
            client = pyodata.Client(service_url, self.session)
            return client
        except pyodata.exceptions.HttpError as e:
            print(f"Error connecting to service {service_name}: {e.response.text}")
            raise

    def execute_query(self, service_name: str = None, entity_set: str = None, **kwargs):
        """Executes a generic OData query."""
        if not service_name or not entity_set:
            return {"error": "Service name and entity set are required for OData queries."}

        try:
            client = self.get_client_for_service(service_name)
            query = getattr(client.entity_sets, entity_set).get_entities()

            if 'select' in kwargs and kwargs['select']:
                query = query.select(kwargs['select'])
            if 'filter' in kwargs and kwargs['filter']:
                query = query.filter(kwargs['filter'])
            if 'top' in kwargs and kwargs['top']:
                query = query.top(kwargs['top'])
            if 'skip' in kwargs and kwargs['skip']:
                query = query.skip(kwargs['skip'])

            result = query.execute()
            return result
        except pyodata.exceptions.HttpError as e:
            return {"error": f"OData Execution Error: {e.response.status_code}", "details": e.response.text}
        except Exception as e:
            return {"error": f"OData Execution Error: {str(e)}"}

    def execute_raw_query(self, query_string: str, prefer_json: bool = False, version: str = "v2"):
        """
        Executes a raw OData GET query string directly.

        Args:
            query_string: Full OData query string (e.g. "SERVICE/EntitySet?$top=10")
            prefer_json: If True, request JSON format
            version: OData version ("v2" or "v4")
        """
        if not self.base_url:
            return {"error": "SAP connection details are missing in environment variables."}

        version = version.lower() if version else "v2"
        if version not in ["v2", "v4"]:
            return {"error": "version must be 'v2' or 'v4'"}

        try:
            if version == "v4":
                v4_base_url = self.base_url.replace("/sap/opu/odata/sap", "/sap/opu/odata4/sap")
                full_url = f"{v4_base_url}/{query_string}"
            else:
                full_url = f"{self.base_url}/{query_string}"

            headers = {
                'Accept': 'application/atom+xml,application/xml,*/*',
                'Content-Type': 'application/json'
            }

            try:
                response = self.session.get(full_url, headers=headers, timeout=90)
                logger.info(f"OData Response status: {response.status_code}")
                response.raise_for_status()

                content_type = response.headers.get('Content-Type', '')

                if 'application/json' in content_type:
                    try:
                        json_response = response.json()
                        if isinstance(json_response, dict) and 'd' in json_response:
                            if '__count' in json_response['d']:
                                count_value = json_response['d']['__count']
                                try:
                                    json_response['count'] = int(count_value) if isinstance(count_value, str) else count_value
                                except (ValueError, TypeError):
                                    pass
                        return json_response
                    except ValueError as e:
                        return {"error": f"OData JSON Parsing Error: {str(e)}", "raw_content": response.text}
                elif 'application/xml' in content_type or 'text/xml' in content_type:
                    return {"result": "XML response received.", "content": response.text}
                else:
                    return {"result": f"Response received with content type: {content_type}.", "content": response.text}

            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response is not None:
                    return {
                        "error": f"OData Execution Error: {e.response.status_code}",
                        "details": e.response.text if hasattr(e.response, 'text') else str(e)
                    }
                return {"error": f"OData Execution Error: {str(e)}"}
        except Exception as e:
            return {"error": f"OData Execution Error: {str(e)}"}

    def execute_raw_post_query(self, query_string: str, data: dict, method: str = "POST", version: str = "v2"):
        """
        Executes a raw OData write query (POST/PUT/PATCH/DELETE).
        Uses a dedicated session for CSRF token + write in one flow.
        """
        if not self.base_url:
            return {"error": "SAP connection details are missing in environment variables."}

        version = version.lower() if version else "v2"
        if version not in ["v2", "v4"]:
            return {"error": "version must be 'v2' or 'v4'"}

        try:
            parts = query_string.split('/')
            if len(parts) < 1:
                return {"error": "Invalid query format. Expected format: SERVICE_NAME/ENTITY_SET"}

            service_name = parts[0]

            post_session = requests.Session()
            post_session.auth = (self.sap_user, self.sap_password)
            post_session.params = {'sap-client': self.sap_client}
            post_session.verify = False

            # Step 1: Get CSRF token
            if version == "v4":
                v4_base_url = self.base_url.replace("/sap/opu/odata/sap", "/sap/opu/odata4/sap")
                csrf_token_url = f"{v4_base_url}/{service_name}/"
            else:
                csrf_token_url = f"{self.base_url}/{service_name}/"

            csrf_headers = {
                'X-CSRF-Token': 'Fetch',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }

            csrf_response = post_session.get(csrf_token_url, headers=csrf_headers, timeout=90)

            if csrf_response.status_code != 200:
                return {"error": f"Failed to retrieve CSRF token: {csrf_response.status_code}"}

            csrf_token = csrf_response.headers.get('X-CSRF-Token')
            if not csrf_token:
                return {"error": "No CSRF token received from server"}

            # Step 2: Execute write request
            if version == "v4":
                full_url = f"{v4_base_url}/{query_string}"
            else:
                full_url = f"{self.base_url}/{query_string}"

            post_headers = {
                'X-CSRF-Token': csrf_token,
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }

            if method.upper() == "POST":
                response = post_session.post(full_url, json=data, headers=post_headers, timeout=90)
            elif method.upper() == "PUT":
                response = post_session.put(full_url, json=data, headers=post_headers, timeout=90)
            elif method.upper() == "PATCH":
                post_headers['If-Match'] = '*'
                response = post_session.patch(full_url, json=data, headers=post_headers, timeout=90)
            elif method.upper() == "DELETE":
                response = post_session.delete(full_url, headers=post_headers, timeout=90)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}

            if response.status_code in [200, 201, 204]:
                if response.text:
                    try:
                        return response.json()
                    except ValueError:
                        return {"result": f"{method} operation completed successfully", "content": response.text}
                else:
                    return {"result": f"{method} operation completed successfully"}
            else:
                return {
                    "error": f"Raw {method} operation failed: {response.status_code}",
                    "details": response.text
                }

        except Exception as e:
            return {"error": f"Raw {method} execution error: {str(e)}"}

    def get_service_metadata(self, service_name: str, query: str = "", version: str = "v2"):
        """Fetches and summarizes OData service metadata with file-based caching."""
        if not self.base_url:
            return {"error": "SAP connection details are missing in environment variables."}

        version = version.lower() if version else "v2"
        if version not in ["v2", "v4"]:
            return {"error": "version must be 'v2' or 'v4'"}

        try:
            from utils import ODataMetadataParser, generate_usage_examples

            cache_dir = "metadata"
            cache_file = os.path.join(cache_dir, f"{service_name}_{version}.xml")
            os.makedirs(cache_dir, exist_ok=True)

            xml_content = None
            cache_used = False

            # Try cache first
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        xml_content = f.read()
                    cache_used = True
                    print(f"Using cached metadata for {service_name}")
                except Exception as e:
                    print(f"Failed to read cached metadata: {str(e)}")
                    xml_content = None

            # Fetch from SAP if not cached
            if xml_content is None:
                if version == "v4":
                    v4_base_url = self.base_url.replace("/sap/opu/odata/sap", "/sap/opu/odata4/sap")
                    metadata_url = f"{v4_base_url}/{service_name}/$metadata"
                else:
                    metadata_url = f"{self.base_url}/{service_name}/$metadata"

                headers = {
                    'Accept': 'application/xml',
                    'Content-Type': 'application/xml'
                }

                try:
                    response = self.session.get(metadata_url, headers=headers, timeout=90)

                    if response.status_code == 200:
                        xml_content = response.text

                        try:
                            with open(cache_file, 'w', encoding='utf-8') as f:
                                f.write(xml_content)
                            print(f"Cached metadata for {service_name}")
                        except Exception as e:
                            print(f"Failed to cache metadata: {str(e)}")
                    else:
                        return {
                            "error": f"Metadata request failed: {response.status_code}",
                            "details": response.text[:500]
                        }

                except requests.exceptions.RequestException as e:
                    if hasattr(e, 'response') and e.response is not None:
                        return {
                            "error": f"Metadata request error: {e.response.status_code}",
                            "details": e.response.text[:500] if hasattr(e.response, 'text') else str(e)
                        }
                    return {"error": f"Metadata request error: {str(e)}"}

            if xml_content is None:
                return {"error": "Failed to retrieve metadata from both cache and SAP endpoint"}

            if isinstance(xml_content, dict) and 'content' in xml_content:
                xml_content = xml_content['content']

            parser = ODataMetadataParser()
            summarized_metadata = parser.parse_metadata_xml(xml_content, query, version, service_name)

            if 'error' in summarized_metadata:
                return summarized_metadata

            # Auto-fallback: if query returned no entities, retry without query
            if query and not summarized_metadata.get('entities'):
                print(f"Query '{query}' returned no entities, falling back to all metadata")
                summarized_metadata = parser.parse_metadata_xml(xml_content, "", version, service_name)
                if 'error' in summarized_metadata:
                    return summarized_metadata

            summarized_metadata['usage_examples'] = generate_usage_examples(summarized_metadata)
            summarized_metadata['_cache_info'] = {'cached': cache_used, 'service': service_name}

            return json.dumps(summarized_metadata, separators=(',', ':'), ensure_ascii=False)

        except Exception as e:
            return {"error": f"Metadata processing error: {str(e)}"}

    def _fetch_f4_entitysets(self, service_path: str, version: str = "v4"):
        """Fetch EntitySet names from an external F4 service's $metadata."""
        if service_path in self.f4_entityset_cache:
            return self.f4_entityset_cache[service_path]

        try:
            if version == "v4":
                v4_base_url = self.base_url.replace("/sap/opu/odata/sap", "/sap/opu/odata4/sap")
                metadata_url = f"{v4_base_url}/{service_path}/$metadata"
            else:
                metadata_url = f"{self.base_url}/{service_path}/$metadata"

            headers = {'Accept': 'application/xml'}

            response = self.session.get(metadata_url, headers=headers, timeout=60)

            if response.status_code == 200:
                root = ET.fromstring(response.content)

                namespaces = {
                    'edmx': 'http://docs.oasis-open.org/odata/ns/edmx',
                    'edm': 'http://docs.oasis-open.org/odata/ns/edm'
                }

                entitysets = []
                for entityset in root.findall('.//edm:EntityContainer/edm:EntitySet', namespaces):
                    name = entityset.get('Name')
                    if name:
                        entitysets.append(name)

                self.f4_entityset_cache[service_path] = entitysets
                return entitysets
            else:
                print(f"Failed to fetch F4 $metadata: {response.status_code}")
                return []

        except Exception as e:
            print(f"Error fetching F4 EntitySets: {str(e)}")
            return []

    def _find_matching_entityset(self, entity_name: str, entitysets: list) -> str:
        """Find best matching EntitySet name from available EntitySets."""
        if not entitysets:
            return None

        entity_lower = entity_name.lower()

        for es in entitysets:
            if es.lower() == entity_lower:
                return es

        property_part = re.sub(r'^[CIP]_|VH$', '', entity_name, flags=re.IGNORECASE)
        property_lower = property_part.lower()

        for es in entitysets:
            es_lower = es.lower()
            if property_lower in es_lower or es_lower in property_lower:
                return es

        prefix = entity_name[:2] if len(entity_name) >= 2 else entity_name[0]
        for es in entitysets:
            if es.startswith(prefix):
                return es

        return entitysets[0]

    def _try_f4_lazy_load(self, service_name: str, entity_name: str, version: str) -> str:
        """Try lazy loading F4 EntitySet on 404 error."""
        entitysets = self._fetch_f4_entitysets(service_name, version)
        if not entitysets:
            return None

        return self._find_matching_entityset(entity_name, entitysets)

    def get_field_values(self, service_name: str, entity_name: str, key_field: str = None, text_field: str = None, max_values: int = None, version: str = "v2", _f4_retry: bool = False):
        """Fetches actual values for dropdown/value list fields from SAP."""
        if not self.base_url:
            return {"error": "SAP connection details are missing in environment variables."}

        version = version.lower() if version else "v2"
        if version not in ["v2", "v4"]:
            return {"error": "version must be 'v2' or 'v4'"}

        try:
            if version == "v4":
                v4_base_url = self.base_url.replace("/sap/opu/odata/sap", "/sap/opu/odata4/sap")
                query_url = f"{v4_base_url}/{service_name}/{entity_name}"
            else:
                query_url = f"{self.base_url}/{service_name}/{entity_name}"

            params = {
                '$top': str(max_values) if max_values is not None else '',
                '$orderby': key_field if key_field else None
            }
            params = {k: v for k, v in params.items() if v is not None}

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }

            try:
                response = self.session.get(query_url, headers=headers, params=params, timeout=60)

                if response.status_code == 200:
                    json_response = response.json()

                    if 'd' in json_response and 'results' in json_response['d']:
                        results = json_response['d']['results']
                    elif 'value' in json_response:
                        results = json_response['value']
                    else:
                        results = json_response if isinstance(json_response, list) else [json_response]

                    if not results:
                        return {"error": "No data found in value list entity"}

                    # Auto-detect key and text fields if not provided
                    if not key_field or not text_field:
                        sample_record = results[0] if results else {}
                        available_fields = list(sample_record.keys())

                        if not key_field:
                            key_field = available_fields[0] if available_fields else None
                            for field in available_fields:
                                if not field.startswith('__') and '_' not in field:
                                    key_field = field
                                    break

                        if not text_field:
                            text_patterns = ['_Text', '_Name', '_Description', '_Desc', 'Desc', 'Text', 'Name', 'Description']
                            for field in available_fields:
                                if any(pattern in field for pattern in text_patterns):
                                    if not any(skip in field.lower() for skip in ['_fc', 'fieldcontrol', 'criticality']):
                                        text_field = field
                                        break

                    processed_values = []
                    for record in results:
                        value_entry = {}
                        if key_field and key_field in record:
                            value_entry['key'] = record[key_field]
                        if text_field and text_field in record:
                            value_entry['text'] = record[text_field]
                        elif key_field and key_field in record:
                            value_entry['text'] = record[key_field]
                        if 'key' in value_entry:
                            processed_values.append(value_entry)

                    return {
                        'entity_name': entity_name,
                        'key_field': key_field,
                        'text_field': text_field,
                        'total_values': len(processed_values),
                        'values': processed_values,
                        'truncated': len(results) >= max_values if max_values else False
                    }

                else:
                    # Try F4 lazy loading on 404 for v4 external F4 services
                    if response.status_code == 404 and version == "v4" and not _f4_retry and '/' in service_name:
                        correct_entity = self._try_f4_lazy_load(service_name, entity_name, version)
                        if correct_entity:
                            return self.get_field_values(
                                service_name, correct_entity, key_field, text_field,
                                max_values, version, _f4_retry=True
                            )

                    return {
                        "error": f"Value list request failed: {response.status_code}",
                        "details": response.text[:500]
                    }

            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 404 and version == "v4" and not _f4_retry and '/' in service_name:
                        correct_entity = self._try_f4_lazy_load(service_name, entity_name, version)
                        if correct_entity:
                            return self.get_field_values(
                                service_name, correct_entity, key_field, text_field,
                                max_values, version, _f4_retry=True
                            )
                    return {
                        "error": f"Value list request error: {e.response.status_code}",
                        "details": e.response.text[:500] if hasattr(e.response, 'text') else str(e)
                    }
                return {"error": f"Value list request error: {str(e)}"}

        except Exception as e:
            return {"error": f"Value list processing error: {str(e)}"}

    def discover_sap_services(self, search: str = None):
        """Discover available SAP business services from the Gateway Service Catalog."""
        if not self.base_url:
            return {"error": "SAP connection details are missing in environment variables."}

        try:
            catalog_url = f"{self.base_url.replace('/sap/opu/odata/sap', '')}/sap/opu/odata/IWFND/CATALOGSERVICE;v=2/ServiceCollection"

            params = {'$format': 'json'}

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }

            try:
                response = self.session.get(catalog_url, headers=headers, params=params, timeout=90)

                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '')

                    if 'application/json' in content_type:
                        json_response = response.json()
                        if 'd' in json_response and 'results' in json_response['d']:
                            services_data = json_response['d']['results']
                        elif 'value' in json_response:
                            services_data = json_response['value']
                        else:
                            services_data = json_response if isinstance(json_response, list) else [json_response]
                    else:
                        try:
                            root = ET.fromstring(response.text)
                            services_data = []
                            for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                                service_info = {}
                                properties = entry.find(
                                    './/{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties')
                                if properties is not None:
                                    for prop in properties:
                                        tag_name = prop.tag.split('}')[-1]
                                        service_info[tag_name] = prop.text if prop.text else ""
                                if service_info:
                                    services_data.append(service_info)
                        except ET.ParseError as e:
                            return {"error": f"Failed to parse XML response: {str(e)}"}

                    if not services_data:
                        return {"found": 0, "sap_services": [], "message": "No SAP services found"}

                    processed_services = []
                    for service in services_data:
                        service_info = {
                            "name": service.get('Name', service.get('Title', service.get('TechnicalServiceName', ''))),
                            "description": service.get('Description', ''),
                            "title": service.get('Title', ''),
                            "service_type": service.get('ServiceType', 'Unknown'),
                            "is_sap_service": service.get('IsSapService', True),
                            "version": service.get('TechnicalServiceVersion', ''),
                            "service_url": service.get('ServiceUrl', ''),
                            "metadata_url": service.get('MetadataUrl', ''),
                            "last_updated": service.get('UpdatedDate', ''),
                            "author": service.get('Author', '')
                        }

                        if not service_info["name"]:
                            continue

                        service_title = service_info["title"]

                        if service_title.startswith("MM_"):
                            service_info["sap_module"] = "Materials Management"
                            service_info["priority"] = "HIGH"
                        elif service_title.startswith("SD_"):
                            service_info["sap_module"] = "Sales & Distribution"
                            service_info["priority"] = "HIGH"
                        elif service_title.startswith("FI_"):
                            service_info["sap_module"] = "Financial Accounting"
                            service_info["priority"] = "HIGH"
                        elif service_title.startswith("API_"):
                            service_info["sap_module"] = "Standard API"
                            service_info["priority"] = "MEDIUM"
                        elif service_title.startswith(("Z", "Y")):
                            service_info["sap_module"] = "Custom"
                            service_info["priority"] = "MEDIUM"
                        else:
                            service_info["sap_module"] = "Other"
                            service_info["priority"] = "MEDIUM"

                        if search:
                            search_lower = search.lower()
                            if (search_lower in service_info["name"].lower() or
                                search_lower in service_info["description"].lower() or
                                    search_lower in service_info["title"].lower()):
                                processed_services.append(service_info)
                        else:
                            processed_services.append(service_info)

                    return {
                        "found": len(processed_services),
                        "sap_services": processed_services,
                        "search_term": search if search else None,
                    }

                else:
                    return {
                        "error": f"Service discovery request failed: {response.status_code}",
                        "details": response.text[:500]
                    }

            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response is not None:
                    return {
                        "error": f"Service discovery request error: {e.response.status_code}",
                        "details": e.response.text[:500] if hasattr(e.response, 'text') else str(e)
                    }
                return {"error": f"Service discovery request error: {str(e)}"}

        except Exception as e:
            return {"error": f"Service discovery processing error: {str(e)}"}


s4_odata_client = S4ODataClient()
