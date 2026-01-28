"""Additional endpoints for category XML import (separate file to avoid conflicts)."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List

import xml.etree.ElementTree as ET
from fastapi import Depends, File, Form, HTTPException, Path, Query, UploadFile, status

from app.deps import get_current_active_user, require_project_admin
from app.db_internal_data import (
    bulk_set_internal_product_categories,
    upsert_internal_categories_tree,
)
from app.schemas.internal_data import (
    CategoryImportIntrospectResponse,
    CategoryImportResult,
    ImportXmlMapping,
    ImportXmlMappingCategories,
    ImportXmlMappingProducts,
)
from app.services.internal_data.category_import import (
    _build_default_yml_mapping,
    detect_xml_format,
    parse_xml_with_mapping,
)

# Import router from main file
from app.routers.internal_data import router


@router.get(
    "/projects/{project_id}/internal-data/categories/import-xml/mapping-template",
    response_model=ImportXmlMapping,
)
async def get_category_import_mapping_template_endpoint(
    project_id: int = Path(..., description="Project ID"),
    format: str = Query("yml", description="Format: yml or 1c"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Get mapping template for category XML import."""
    if format == "yml":
        mapping = _build_default_yml_mapping()
        return ImportXmlMapping(**mapping)
    elif format == "1c":
        # Return empty template for 1C (user must configure)
        return ImportXmlMapping(
            format="1c",
            categories=ImportXmlMappingCategories(
                node_xpath="",
                key_xpath="",
                name_xpath="",
                parent_key_xpath=None,
            ),
            products=ImportXmlMappingProducts(
                node_xpath="",
                sku_xpath="",
                category_key_xpath="",
                category_name_fallback_xpath=None,
            ),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be 'yml' or '1c'",
        )


@router.post(
    "/projects/{project_id}/internal-data/categories/import-xml/introspect",
    response_model=CategoryImportIntrospectResponse,
)
async def introspect_category_import_xml_endpoint(
    project_id: int = Path(..., description="Project ID"),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Introspect XML file to help configure mapping."""
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".xml") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        xml_text = content.decode("utf-8")
        
        # Detect format
        detected_format = detect_xml_format(xml_text)
        
        # Parse XML for introspection
        root = ET.fromstring(xml_text)
        
        # Find category candidates (look for common patterns)
        category_candidates = []
        product_candidates = []
        category_samples = []
        product_samples = []
        
        # Common YML patterns
        yml_cat_paths = [
            "/yml_catalog/shop/categories/category",
            "//category",
            "//categories/category",
        ]
        yml_prod_paths = [
            "/yml_catalog/shop/offers/offer",
            "//offer",
            "//offers/offer",
        ]
        
        # Common 1C patterns
        c1_cat_paths = [
            "//Группа",
            "//Группы/Группа",
            "//Классификатор/Группы/Группа",
        ]
        c1_prod_paths = [
            "//Товар",
            "//Товары/Товар",
            "//Каталог/Товары/Товар",
        ]
        
        # Try to find categories
        for path in yml_cat_paths + c1_cat_paths:
            try:
                elems = root.findall(path)
                if elems:
                    category_candidates.append({
                        "path": path,
                        "count": len(elems),
                        "sample_attrs": list(elems[0].attrib.keys())[:5] if elems[0].attrib else [],
                    })
                    if len(category_samples) < 3:
                        cat_elem = elems[0]
                        sample = {
                            "tag": cat_elem.tag,
                            "attributes": dict(cat_elem.attrib),
                            "text": (cat_elem.text or "").strip()[:100],
                        }
                        category_samples.append(sample)
                    break
            except Exception:
                continue
        
        # Try to find products
        for path in yml_prod_paths + c1_prod_paths:
            try:
                elems = root.findall(path)
                if elems:
                    product_candidates.append({
                        "path": path,
                        "count": len(elems),
                        "sample_attrs": list(elems[0].attrib.keys())[:5] if elems[0].attrib else [],
                    })
                    if len(product_samples) < 3:
                        prod_elem = elems[0]
                        sample = {
                            "tag": prod_elem.tag,
                            "attributes": dict(prod_elem.attrib),
                            "text": (prod_elem.text or "").strip()[:100],
                            "children": [child.tag for child in list(prod_elem)[:5]],
                        }
                        product_samples.append(sample)
                    break
            except Exception:
                continue
        
        # Get default mapping
        default_mapping = {}
        if detected_format == "yml":
            default_mapping = _build_default_yml_mapping()
        
        return CategoryImportIntrospectResponse(
            detected_format=detected_format,
            category_candidates=category_candidates,
            product_candidates=product_candidates,
            category_samples=category_samples,
            product_samples=product_samples,
            default_mapping=default_mapping,
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post(
    "/projects/{project_id}/internal-data/categories/import-xml",
    response_model=CategoryImportResult,
)
async def import_category_xml_endpoint(
    project_id: int = Path(..., description="Project ID"),
    file: UploadFile = File(...),
    mapping_json: str | None = Form(None, description="Optional mapping JSON string"),
    format: str = Query("auto", description="Format: auto, yml, or 1c"),
    mode: str = Query("categories_and_products", description="Mode: categories_only or categories_and_products"),
    create_missing_categories: bool = Query(True, description="Create categories if not found"),
    on_unknown_sku: str = Query("skip", description="Action on unknown SKU: skip or error"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Import categories and/or product-category links from XML."""
    # Validate parameters
    if mode not in ("categories_only", "categories_and_products"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be 'categories_only' or 'categories_and_products'",
        )
    
    if on_unknown_sku not in ("skip", "error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="on_unknown_sku must be 'skip' or 'error'",
        )
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".xml") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        xml_text = content.decode("utf-8")
        
        # Detect or use specified format
        if format == "auto":
            detected_format = detect_xml_format(xml_text)
        elif format in ("yml", "1c"):
            detected_format = format
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="format must be 'auto', 'yml', or '1c'",
            )
        
        # Get mapping
        if mapping_json:
            try:
                mapping_dict = json.loads(mapping_json)
                mapping = ImportXmlMapping(**mapping_dict)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid mapping_json: {e}",
                ) from e
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid mapping structure: {e}",
                ) from e
        else:
            # Use default for YML, require mapping for 1C
            if detected_format == "yml":
                mapping_dict = _build_default_yml_mapping()
                mapping = ImportXmlMapping(**mapping_dict)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="mapping_json is required for 1C format. Use introspect endpoint to help configure.",
                )
        
        # Parse XML
        try:
            categories, links = parse_xml_with_mapping(xml_text, mapping.model_dump())
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"XML parsing error: {e}",
            ) from e
        
        errors_first_n: List[Dict[str, Any]] = []
        categories_total = len(categories)
        categories_created = 0
        categories_updated = 0
        products_total_rows = len(links)
        products_updated = 0
        missing_sku: List[str] = []
        missing_category: List[str] = []
        key_to_id: Dict[str, int] = {}
        
        # Import categories
        if categories and mode in ("categories_only", "categories_and_products"):
            try:
                result = upsert_internal_categories_tree(project_id, categories)
                categories_created = result["created"]
                categories_updated = result["updated"]
                key_to_id = result["key_to_id"]
            except Exception as e:
                errors_first_n.append({
                    "type": "category_import_error",
                    "message": str(e),
                })
        
        # Import product-category links
        if links and mode == "categories_and_products":
            # Create missing categories if requested
            if create_missing_categories:
                category_keys_in_db = set(key_to_id.keys())
                category_keys_in_links = {link.get("category_key") for link in links if link.get("category_key")}
                missing_keys = category_keys_in_links - category_keys_in_db
                
                if missing_keys:
                    # Create missing categories with key=name
                    missing_cats = []
                    seen_keys = set()
                    for link in links:
                        cat_key = link.get("category_key")
                        if cat_key and cat_key in missing_keys and cat_key not in seen_keys:
                            missing_cats.append({
                                "key": cat_key,
                                "name": cat_key,  # Use key as name
                                "parent_key": None,
                                "meta_json": {},
                            })
                            seen_keys.add(cat_key)
                    
                    if missing_cats:
                        try:
                            result = upsert_internal_categories_tree(project_id, missing_cats)
                            categories_created += result["created"]
                            categories_updated += result["updated"]
                            key_to_id.update(result["key_to_id"])
                        except Exception as e:
                            errors_first_n.append({
                                "type": "missing_category_creation_error",
                                "message": str(e),
                            })
            
            # Bulk set product categories
            try:
                result = bulk_set_internal_product_categories(
                    project_id,
                    links,
                    on_unknown_sku=on_unknown_sku,
                )
                products_updated = result["updated"]
                missing_sku = result["missing_sku"][:200]  # Limit
                missing_category = result["missing_category"][:200]  # Limit
                
                # Add to errors if any
                for sku in missing_sku[:50]:  # First 50
                    errors_first_n.append({
                        "type": "missing_sku",
                        "sku": sku,
                        "message": f"Product not found: {sku}",
                    })
                
                for cat_key in missing_category[:50]:  # First 50
                    errors_first_n.append({
                        "type": "missing_category",
                        "category_key": cat_key,
                        "message": f"Category not found: {cat_key}",
                    })
            except ValueError as e:
                if on_unknown_sku == "error":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=str(e),
                    ) from e
                errors_first_n.append({
                    "type": "product_category_error",
                    "message": str(e),
                })
            except Exception as e:
                errors_first_n.append({
                    "type": "product_category_error",
                    "message": str(e),
                })
        
        # Limit errors
        errors_first_n = errors_first_n[:200]
        
        return CategoryImportResult(
            categories_total=categories_total,
            categories_created=categories_created,
            categories_updated=categories_updated,
            products_total_rows=products_total_rows,
            products_updated=products_updated,
            missing_sku=missing_sku,
            missing_category=missing_category,
            errors_first_n=errors_first_n,
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
