import csv
import io
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
import re


class ODataMetadataParser:
    """Parser for OData metadata XML that extracts minimal essential information with annotations."""

    def __init__(self):
        self.namespaces = {
            'edmx': 'http://schemas.microsoft.com/ado/2007/06/edmx',
            'edm': 'http://schemas.microsoft.com/ado/2008/09/edm',
            'm': 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata',
            'sap': 'http://www.sap.com/Protocols/SAPData'
        }

        self.v4_namespaces = {
            'edmx': 'http://docs.oasis-open.org/odata/ns/edmx',
            'edm': 'http://docs.oasis-open.org/odata/ns/edm',
            'sap': 'http://www.sap.com/Protocols/SAPData'
        }

        self.v2_namespaces = {
            'edmx': 'http://schemas.microsoft.com/ado/2007/06/edmx',
            'edm': 'http://schemas.microsoft.com/ado/2008/09/edm',
            'm': 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata',
            'sap': 'http://www.sap.com/Protocols/SAPData'
        }

    def parse_metadata_xml(self, xml_content: str, query: str = "", version: str = "v2", service_path: str = "") -> Dict[str, Any]:
        try:
            xml_content = self._clean_xml_content(xml_content)
            root = ET.fromstring(xml_content)

            self._set_namespaces_for_version(version)

            service_name = self._extract_service_name(root)

            self.current_service_path = service_path

            annotations = self._extract_annotations(root)

            entities = self._extract_entities(root, annotations)

            if query:
                entities = self._filter_entities(entities, query)

            return {
                'service': service_name,
                'entities': entities
            }

        except ET.ParseError as e:
            return {'error': f'XML parsing error: {str(e)}'}
        except Exception as e:
            return {'error': f'Metadata parsing error: {str(e)}'}

    def _set_namespaces_for_version(self, version: str) -> None:
        if version == "v4":
            self.namespaces = self.v4_namespaces.copy()
        else:
            self.namespaces = self.v2_namespaces.copy()

    def _clean_xml_content(self, xml_content: str) -> str:
        if xml_content.startswith('﻿'):
            xml_content = xml_content[1:]
        return xml_content

    def _extract_service_name(self, root: ET.Element) -> str:
        schema = root.find('.//edm:Schema', self.namespaces)
        if schema is not None:
            return schema.get('Namespace', 'Unknown')
        return 'Unknown'

    def _extract_annotations(self, root: ET.Element) -> Dict[str, Dict[str, Any]]:
        annotations = {}

        for annotation_group in root.findall('.//edm:Annotations', self.namespaces):
            target = annotation_group.get('Target', '')
            if not target:
                continue

            if '/' in target:
                entity_part, field_name = target.rsplit('/', 1)
                entity_name = entity_part.split(
                    '.')[-1] if '.' in entity_part else entity_part

                if entity_name not in annotations:
                    annotations[entity_name] = {}
                if field_name not in annotations[entity_name]:
                    annotations[entity_name][field_name] = {}

                for annotation in annotation_group.findall('.//edm:Annotation', self.namespaces):
                    term = annotation.get('Term', '')

                    if term == 'Common.Label':
                        label = annotation.get('String', '')
                        if label:
                            annotations[entity_name][field_name]['label'] = label

                    elif term == 'Common.FieldControl':
                        enum_member = annotation.get('EnumMember', '')
                        if 'Mandatory' in enum_member:
                            annotations[entity_name][field_name]['required'] = True

                    elif term == 'Common.ValueList':
                        collection_path = self._extract_collection_path(annotation)
                        if collection_path:
                            annotations[entity_name][field_name]['values_from'] = collection_path

                    elif term == 'SAP__common.ValueListReferences':
                        f4_info = self._extract_f4_reference(annotation, field_name)
                        if f4_info:
                            if 'service_path' in f4_info:
                                annotations[entity_name][field_name]['f4_service'] = f4_info['service_path']
                            if 'collection_path' in f4_info:
                                annotations[entity_name][field_name]['f4_collection'] = f4_info['collection_path']

        return annotations

    def _extract_collection_path(self, annotation: ET.Element) -> Optional[str]:
        for record in annotation.findall('.//edm:Record', self.namespaces):
            for prop_value in record.findall('.//edm:PropertyValue', self.namespaces):
                if prop_value.get('Property') == 'CollectionPath':
                    return prop_value.get('String')
        return None

    def _extract_f4_reference(self, annotation: ET.Element, property_name: str) -> Optional[Dict[str, str]]:
        f4_info = {}

        for collection in annotation.findall('.//edm:Collection', self.namespaces):
            for string_elem in collection.findall('.//edm:String', self.namespaces):
                url_text = string_elem.text
                if url_text:
                    url_text = url_text.replace('../../../../', '').replace('/$metadata', '')

                    f4_path_with_params = url_text

                    f4_base_path = url_text.split(';')[0] if ';' in url_text else url_text

                    path_parts = f4_base_path.split('/')
                    if len(path_parts) >= 3:
                        service_name = path_parts[-2]

                        if service_name.startswith(('c_', 'i_', 'p_')):
                            prefix = service_name[0].upper() + '_'
                            collection_name = f"{prefix}{property_name}VH"
                        else:
                            collection_name = f"{property_name}VH"

                        parent_base = ""
                        if hasattr(self, 'current_service_path') and self.current_service_path:
                            parent_base = self.current_service_path.split('/')[0]

                        if parent_base:
                            complete_service_path = f"{parent_base}/{f4_path_with_params}"
                        else:
                            complete_service_path = f4_path_with_params

                        from urllib.parse import quote
                        encoded_service_path = quote(complete_service_path, safe='/;=')

                        f4_info['service_path'] = encoded_service_path
                        f4_info['collection_path'] = collection_name

                        break

            if f4_info:
                break

        return f4_info if f4_info else None

    def _is_dummy_label(self, label: str) -> bool:
        if not label:
            return True

        dummy_patterns = ['dyn. ']

        label_lower = label.lower().strip()

        for pattern in dummy_patterns:
            if label_lower.startswith(pattern):
                return True

        if len(label_lower) <= 2:
            return True

        return False

    def _extract_field_keywords(self, field_name: str) -> list:
        words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', field_name)
        common_words = {'and', 'or', 'by', 'to', 'from', 'with', 'in', 'on', 'at', 'the', 'a', 'is'}
        keywords = [word.lower() for word in words if word.lower() not in common_words and len(word) > 2]
        return keywords

    def _extract_entities(self, root: ET.Element, annotations: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        entities = {}

        entity_sets = {}
        for entity_set in root.findall('.//edm:EntitySet', self.namespaces):
            set_name = entity_set.get('Name')
            entity_type = entity_set.get('EntityType', '')
            type_name = entity_type.split('.')[-1] if '.' in entity_type else entity_type
            entity_sets[type_name] = set_name

        nav_to_target = {}
        for association in root.findall('.//edm:Association', self.namespaces):
            for end in association.findall('edm:End', self.namespaces):
                role = end.get('Role')
                entity_type_full = end.get('Type', '')
                if role and role.startswith('ToRole_'):
                    target_type = entity_type_full.split('.')[-1] if '.' in entity_type_full else entity_type_full
                    assoc_name = association.get('Name')
                    if assoc_name:
                        nav_to_target[assoc_name] = target_type

        nav_prop_to_entity_set = {}
        for entity_type in root.findall('.//edm:EntityType', self.namespaces):
            for nav_prop in entity_type.findall('edm:NavigationProperty', self.namespaces):
                nav_name = nav_prop.get('Name')
                relationship = nav_prop.get('Relationship', '')
                assoc_name = relationship.split('.')[-1] if '.' in relationship else relationship
                if nav_name and assoc_name in nav_to_target:
                    target_type = nav_to_target[assoc_name]
                    target_set_name = entity_sets.get(target_type, target_type)
                    nav_prop_to_entity_set[nav_name] = target_set_name

        for entity_type in root.findall('.//edm:EntityType', self.namespaces):
            type_name = entity_type.get('Name')
            if not type_name:
                continue

            entity_set_name = entity_sets.get(type_name, type_name)

            entity_info = {'k': [], 'f': {}}

            entity_sap_label = entity_type.get(
                '{http://www.sap.com/Protocols/SAPData}label')
            if entity_sap_label:
                entity_info['l'] = entity_sap_label

            type_name_lower = type_name.lower()
            has_vh_name = (
                'valuehelp' in type_name_lower or
                'valhelp' in type_name_lower or
                type_name_lower.endswith('vh')
            )

            entity_value_list = entity_type.get(
                '{http://www.sap.com/Protocols/SAPData}value-list')
            has_vh_attribute = entity_value_list == 'true'

            if has_vh_name or has_vh_attribute:
                entity_info['vh'] = 1

            key_element = entity_type.find('edm:Key', self.namespaces)
            if key_element is not None:
                for prop_ref in key_element.findall('edm:PropertyRef', self.namespaces):
                    key_name = prop_ref.get('Name')
                    if key_name:
                        entity_info['k'].append(key_name)

            for prop in entity_type.findall('edm:Property', self.namespaces):
                field_name = prop.get('Name')
                if not field_name:
                    continue

                field_info = {}

                nullable = prop.get('Nullable', 'true')
                if nullable == 'false':
                    field_info['r'] = 1

                sap_label = prop.get('{http://www.sap.com/Protocols/SAPData}label')
                if sap_label and not self._is_dummy_label(sap_label):
                    field_info['l'] = sap_label

                sap_value_list = prop.get('{http://www.sap.com/Protocols/SAPData}value-list')
                if sap_value_list in ('true', 'fixed-values', 'standard'):
                    field_info['vh'] = 1

                sap_quickinfo = prop.get('{http://www.sap.com/Protocols/SAPData}quickinfo')
                if sap_quickinfo and sap_quickinfo != sap_label:
                    field_info['d'] = sap_quickinfo

                if type_name in annotations and field_name in annotations[type_name]:
                    field_annotations = annotations[type_name][field_name]
                    if 'label' in field_annotations:
                        field_info['l'] = field_annotations['label']
                    if 'required' in field_annotations:
                        field_info['r'] = 1

                    if 'values_from' in field_annotations:
                        field_info['vh'] = {
                            'type': 'internal',
                            'entity': field_annotations['values_from']
                        }
                    elif 'f4_service' in field_annotations and 'f4_collection' in field_annotations:
                        field_info['vh'] = {
                            'type': 'external',
                            'service_path': field_annotations['f4_service'],
                            'entity': field_annotations['f4_collection']
                        }

                if field_info:
                    entity_info['f'][field_name] = field_info

            nav_props = []
            for nav_prop in entity_type.findall('edm:NavigationProperty', self.namespaces):
                nav_name = nav_prop.get('Name')
                if nav_name:
                    nav_props.append(nav_name)

            if nav_props:
                entity_info['n'] = nav_props

            for field_name, field_info in entity_info['f'].items():
                if field_info.get('vh') == 1 and 'v' not in field_info:
                    field_keywords = self._extract_field_keywords(field_name)

                    for nav_name in nav_props:
                        target_entity_set = nav_prop_to_entity_set.get(nav_name)
                        if not target_entity_set:
                            continue

                        nav_name_lower = nav_name.lower()
                        if 'valuehelp' in nav_name_lower or 'valhelp' in nav_name_lower:
                            if any(keyword in nav_name_lower for keyword in field_keywords):
                                field_info['v'] = target_entity_set
                                break

            entities[entity_set_name] = entity_info

        return entities

    def _filter_entities(self, entities: Dict[str, Any], query: str) -> Dict[str, Any]:
        if not query or not entities:
            return entities

        query_lower = query.lower().strip()
        filtered_entities = {}

        for entity_name, entity_info in entities.items():
            entity_matches = False
            filtered_fields = {}

            if query_lower in entity_name.lower():
                entity_matches = True
                filtered_fields = entity_info.get('f', {})
            else:
                entity_label = entity_info.get('l', '')
                if entity_label and query_lower in entity_label.lower():
                    entity_matches = True
                    filtered_fields = entity_info.get('f', {})

            if not entity_matches:
                for field_name, field_info in entity_info.get('f', {}).items():
                    field_matches = False

                    if query_lower in field_name.lower():
                        field_matches = True

                    field_label = field_info.get('l', '')
                    if field_label and query_lower in field_label.lower():
                        field_matches = True

                    field_desc = field_info.get('d', '')
                    if field_desc and query_lower in field_desc.lower():
                        field_matches = True

                    values_from = field_info.get('v', '')
                    if values_from and query_lower in values_from.lower():
                        field_matches = True

                    if field_matches:
                        filtered_fields[field_name] = field_info
                        entity_matches = True

            if entity_matches:
                filtered_entity_info = entity_info.copy()
                filtered_entity_info['f'] = filtered_fields
                filtered_entities[entity_name] = filtered_entity_info

        return filtered_entities


def generate_usage_examples(metadata_summary: Dict[str, Any]) -> List[str]:
    examples = []

    if 'entities' in metadata_summary:
        entity_names = list(metadata_summary['entities'].keys())[:3]

        for entity_name in entity_names:
            entity = metadata_summary['entities'][entity_name]

            examples.append(f"GET /{entity_name}")

            if entity.get('k'):
                key_fields = ','.join(entity['k'][:2])
                examples.append(
                    f"GET /{entity_name}?$select={key_fields}&$top=10")

            if entity.get('k'):
                first_key = entity['k'][0]
                examples.append(
                    f"GET /{entity_name}?$filter={first_key} eq 'value'&$top=5")

    return examples


def convert_to_csv(data):
    """Convert OData response (XML or JSON) to CSV format with total count header."""
    if not data:
        return "# Total Count: 0\n"

    if isinstance(data, dict) and 'error' in data:
        return f"# Total Count: 0\n# Error: {data.get('error', 'Unknown error')}\n"

    # JSON response (OData v4 format: {value: [...]})
    if isinstance(data, dict) and 'value' in data and isinstance(data['value'], list):
        results_data = data['value']
        total_count = data.get('@odata.count', len(results_data))

        if not results_data:
            return f"# Total Count: {total_count}\n"

        clean_results = []
        for item in results_data:
            if isinstance(item, dict):
                clean_item = {k: v for k, v in item.items() if not k.startswith('@') and not k.startswith('SAP__')}
                clean_results.append(clean_item)

        if not clean_results:
            return f"# Total Count: {total_count}\n"

        all_keys = set()
        for item in clean_results:
            all_keys.update(item.keys())

        output = io.StringIO()
        output.write(f"# Total Count: {total_count}\n")
        writer = csv.DictWriter(output, fieldnames=sorted(all_keys))
        writer.writeheader()
        for item in clean_results:
            writer.writerow(item)
        return output.getvalue()

    # JSON response (OData v2 format: {d: {results: [...]}})
    if isinstance(data, dict) and 'd' in data:
        try:
            d_data = data['d']

            if isinstance(d_data, dict) and 'results' in d_data:
                results_data = d_data['results']
            elif isinstance(d_data, list):
                results_data = d_data
            else:
                results_data = [d_data]

            total_count = d_data.get('__count', len(results_data)) if isinstance(d_data, dict) else len(results_data)

            if not results_data:
                return f"# Total Count: {total_count}\n"

            clean_results = []
            for item in results_data:
                if isinstance(item, dict):
                    clean_item = {k: v for k, v in item.items() if not k.startswith('__')}
                    clean_results.append(clean_item)

            if not clean_results:
                return f"# Total Count: {total_count}\n"

            all_keys = set()
            for item in clean_results:
                all_keys.update(item.keys())

            if not all_keys:
                return f"# Total Count: {total_count}\n"

            output = io.StringIO()
            output.write(f"# Total Count: {total_count}\n")

            writer = csv.DictWriter(output, fieldnames=sorted(all_keys))
            writer.writeheader()

            for item in clean_results:
                writer.writerow(item)

            return output.getvalue()

        except Exception as e:
            print(f"Warning: Failed to convert JSON to CSV: {e}")
            return f"# Total Count: 0\n# Error parsing JSON: {str(e)}\n"

    # XML response (wrapped in dict with 'content' key)
    if isinstance(data, dict) and 'content' in data and isinstance(data.get('content'), str):
        xml_content = data['content']
        if xml_content.strip().startswith('<'):
            try:
                root = ET.fromstring(xml_content)

                namespaces = {
                    'atom': 'http://www.w3.org/2005/Atom',
                    'd': 'http://schemas.microsoft.com/ado/2007/08/dataservices',
                    'm': 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata'
                }

                total_count = 0
                if '</m:count>' in xml_content:
                    count_match = re.search(r'<m:count>(\d+)</m:count>', xml_content)
                    if count_match:
                        total_count = int(count_match.group(1))

                entries = root.findall('.//atom:entry', namespaces)
                if total_count == 0:
                    total_count = len(entries)

                if not entries:
                    return f"# Total Count: {total_count}\n"

                results_data = []
                for entry in entries:
                    entry_data = {}

                    properties = entry.find('.//m:properties', namespaces)
                    if properties is not None:
                        for prop in properties:
                            tag_name = prop.tag.split('}')[-1] if '}' in prop.tag else prop.tag
                            entry_data[tag_name] = prop.text if prop.text is not None else ""

                    if entry_data:
                        results_data.append(entry_data)

                if not results_data:
                    return f"# Total Count: {total_count}\n"

                all_keys = set()
                for item in results_data:
                    all_keys.update(item.keys())

                if not all_keys:
                    return f"# Total Count: {total_count}\n"

                output = io.StringIO()
                output.write(f"# Total Count: {total_count}\n")

                writer = csv.DictWriter(output, fieldnames=sorted(all_keys))
                writer.writeheader()

                for item in results_data:
                    writer.writerow(item)

                return output.getvalue()

            except Exception as e:
                print(f"Warning: Failed to convert XML to CSV: {e}")
                return f"# Total Count: 0\n# Error parsing XML: {str(e)}\n"

    return "# Total Count: 0\n# Unexpected response format\n"
