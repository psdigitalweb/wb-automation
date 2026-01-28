"""XML category import parser for Internal Data categories and product categorization.

Supports YML (Yandex Market) and 1C XML formats with configurable mapping.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple


def detect_xml_format(xml_text: str) -> str:
    """Detect XML format by root tags and structure.
    
    Returns:
        "yml" for Yandex Market XML, "1c" for 1C XML, or raises ValueError
    """
    try:
        root = ET.fromstring(xml_text[:5000])  # Sample first 5KB
    except ET.ParseError:
        raise ValueError("Invalid XML format")
    
    # Check for YML structure
    if root.tag == "yml_catalog" or root.find(".//{*}yml_catalog") is not None:
        return "yml"
    
    # Check for 1C structure (common patterns)
    if root.tag in ("Каталог", "Классификатор", "КоммерческаяИнформация"):
        return "1c"
    
    # Check for common 1C namespaces
    if any("1c.ru" in ns or "v8.1c.ru" in ns for ns in root.attrib.values() if isinstance(ns, str)):
        return "1c"
    
    raise ValueError("Unknown XML format. Expected YML (yml_catalog) or 1C (Каталог/Классификатор)")


def _simple_xpath_find(elem: ET.Element, xpath: str) -> Optional[str]:
    """Simple XPath-like finder for ElementTree.
    
    Supports:
    - Simple paths: "category", "shop/categories/category"
    - Attributes: "@id", "category/@id"
    - Text content: "text()", "name/text()"
    
    Args:
        elem: Element to search from
        xpath: XPath-like expression
        
    Returns:
        String value or None
    """
    if not xpath or not xpath.strip():
        return None
    
    xpath = xpath.strip()
    
    # Handle text() at the end
    if xpath.endswith("/text()"):
        path = xpath[:-7].strip()
        if not path:
            return (elem.text or "").strip() or None
        target = elem
        for part in path.split("/"):
            if not part:
                continue
            target = target.find(part)
            if target is None:
                return None
        return (target.text or "").strip() or None
    
    # Handle @attribute
    if xpath.startswith("@"):
        attr_name = xpath[1:]
        return elem.attrib.get(attr_name) or None
    
    # Handle path/@attribute
    if "/@" in xpath:
        path, attr = xpath.rsplit("/@", 1)
        target = elem
        for part in path.split("/"):
            if not part:
                continue
            target = target.find(part)
            if target is None:
                return None
        return target.attrib.get(attr) or None
    
    # Handle simple path
    parts = [p for p in xpath.split("/") if p]
    target = elem
    for part in parts:
        target = target.find(part)
        if target is None:
            return None
    
    # Return text content if found
    return (target.text or "").strip() or None


def _find_all_by_path(root: ET.Element, xpath: str) -> List[ET.Element]:
    """Find all elements matching XPath-like path.
    
    Args:
        root: Root element
        xpath: XPath-like expression (without @ or text())
        
    Returns:
        List of matching elements
    """
    # Remove @ and text() for path finding
    path = xpath.split("/@")[0].replace("/text()", "").strip()
    if not path:
        return []
    
    # Handle absolute path starting with /
    if path.startswith("/"):
        path = path[1:]
        # Find from root
        parts = [p for p in path.split("/") if p]
        if not parts:
            return [root]
        current = root
        for part in parts[:-1]:
            found = current.find(part)
            if found is None:
                return []
            current = found
        return current.findall(parts[-1])
    
    # Relative path from root
    parts = [p for p in path.split("/") if p]
    if not parts:
        return []
    
    current = root
    for part in parts[:-1]:
        found = current.find(part)
        if found is None:
            return []
        current = found
    
    return current.findall(parts[-1])


def _build_default_yml_mapping() -> Dict[str, Any]:
    """Build default mapping for YML format."""
    return {
        "format": "yml",
        "categories": {
            "node_xpath": "/yml_catalog/shop/categories/category",
            "key_xpath": "@id",
            "name_xpath": "text()",
            "parent_key_xpath": "@parentId",
        },
        "products": {
            "node_xpath": "/yml_catalog/shop/offers/offer",
            "sku_xpath": "vendorCode",
            "category_key_xpath": "categoryId",
        },
    }


def parse_xml_with_mapping(
    xml_text: str,
    mapping: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse XML with mapping configuration.
    
    Args:
        xml_text: XML content as string
        mapping: Mapping configuration (ImportXmlMapping schema)
        
    Returns:
        Tuple of (categories, links) where:
        - categories: List of {key, name, parent_key, meta_json}
        - links: List of {internal_sku, category_key, meta_json}
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}") from e
    
    categories: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    
    cat_config = mapping.get("categories", {})
    prod_config = mapping.get("products", {})
    
    # Parse categories
    if cat_config:
        cat_node_xpath = cat_config.get("node_xpath", "")
        if cat_node_xpath:
            cat_nodes = _find_all_by_path(root, cat_node_xpath)
            
            for cat_elem in cat_nodes:
                key = _simple_xpath_find(cat_elem, cat_config.get("key_xpath", ""))
                name = _simple_xpath_find(cat_elem, cat_config.get("name_xpath", ""))
                parent_key = _simple_xpath_find(cat_elem, cat_config.get("parent_key_xpath", ""))
                
                if not key:
                    continue  # Skip categories without key
                
                # Build meta_json from extra_meta_xpaths if any
                meta_json: Dict[str, Any] = {}
                extra_meta = cat_config.get("extra_meta_xpaths", {})
                if isinstance(extra_meta, dict):
                    for meta_key, meta_xpath in extra_meta.items():
                        meta_value = _simple_xpath_find(cat_elem, meta_xpath)
                        if meta_value:
                            meta_json[meta_key] = meta_value
                
                categories.append({
                    "key": key,
                    "name": name or key,  # Fallback to key if name missing
                    "parent_key": parent_key if parent_key else None,
                    "meta_json": meta_json,
                })
            
            # Note: If parent_key_xpath is empty, parent_key will remain None
            # Hierarchy inference from XML structure is complex without lxml
            # Users should provide parent_key_xpath in mapping for hierarchical categories
    
    # Parse product-category links
    if prod_config:
        prod_node_xpath = prod_config.get("node_xpath", "")
        if prod_node_xpath:
            prod_nodes = _find_all_by_path(root, prod_node_xpath)
            
            for prod_elem in prod_nodes:
                sku = _simple_xpath_find(prod_elem, prod_config.get("sku_xpath", ""))
                category_key = _simple_xpath_find(prod_elem, prod_config.get("category_key_xpath", ""))
                
                if not sku:
                    continue  # Skip products without SKU
                
                # If category_key not found, try fallback
                if not category_key and prod_config.get("category_name_fallback_xpath"):
                    category_name = _simple_xpath_find(prod_elem, prod_config["category_name_fallback_xpath"])
                    if category_name:
                        # Use name as key (will need to be created if create_missing_categories=True)
                        category_key = category_name
                
                if category_key:
                    # Build meta_json from extra_meta_xpaths if any
                    meta_json: Dict[str, Any] = {}
                    extra_meta = prod_config.get("extra_meta_xpaths", {})
                    if isinstance(extra_meta, dict):
                        for meta_key, meta_xpath in extra_meta.items():
                            meta_value = _simple_xpath_find(prod_elem, meta_xpath)
                            if meta_value:
                                meta_json[meta_key] = meta_value
                    
                    links.append({
                        "internal_sku": sku,
                        "category_key": category_key,
                        "meta_json": meta_json,
                    })
    
    return categories, links
