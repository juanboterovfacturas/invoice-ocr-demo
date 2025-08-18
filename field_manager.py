import json
import os
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class FieldDefinition:
    """Represents a field that can be extracted from invoices"""
    name: str
    label: str
    description: str
    data_type: str  # text, number, date, currency, array
    required: bool = False
    default_value: str = ""
    validation_rules: Dict[str, Any] = None
    extraction_hints: str = ""  # Additional hints for AI extraction
    
    def __post_init__(self):
        if self.validation_rules is None:
            self.validation_rules = {}

class FieldConfigManager:
    """Manages field configurations for invoice extraction"""
    
    def __init__(self, config_file: str = "field_config.json"):
        self.config_file = config_file
        self.fields: Dict[str, FieldDefinition] = {}
        self.presets: Dict[str, List[str]] = {}
        self.load_config()
    
    def load_config(self):
        """Load field configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Load fields
                for field_data in data.get('fields', []):
                    field = FieldDefinition(**field_data)
                    self.fields[field.name] = field
                    
                # Load presets
                self.presets = data.get('presets', {})
                
            except Exception as e:
                print(f"Error loading field config: {e}")
                self.load_default_fields()
        else:
            self.load_default_fields()
    
    def save_config(self):
        """Save field configuration to file"""
        try:
            data = {
                'fields': [asdict(field) for field in self.fields.values()],
                'presets': self.presets
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving field config: {e}")
    
    def load_default_fields(self):
        """Load default invoice fields"""
        default_fields = [
            FieldDefinition(
                name="invoice_type",
                label="Invoice Type",
                description="Type of invoice (e.g., Commercial, Sales Tax, Proforma)",
                data_type="text",
                required=True,
                extraction_hints="Look for document headers or titles"
            ),
            FieldDefinition(
                name="invoice_number",
                label="Invoice Number",
                description="Unique identifier for the invoice",
                data_type="text",
                required=True,
                extraction_hints="Usually labeled as 'Invoice No', 'Bill No', or 'Doc No'"
            ),
            FieldDefinition(
                name="buyer_name",
                label="Buyer Name",
                description="Name of the purchasing company or individual",
                data_type="text",
                required=True,
                extraction_hints="May be labeled as 'Buyer', 'Customer', 'Bill To', or 'Sold To'"
            ),
            FieldDefinition(
                name="supplier_name",
                label="Supplier Name",
                description="Name of the selling company or individual",
                data_type="text",
                required=True,
                extraction_hints="Usually at the top of invoice, may be in header or labeled as 'Seller'"
            ),
            FieldDefinition(
                name="invoice_date",
                label="Invoice Date",
                description="Date when the invoice was issued",
                data_type="date",
                required=True,
                validation_rules={"format": "DD-MM-YYYY"},
                extraction_hints="Convert any date format to DD-MM-YYYY"
            ),
            FieldDefinition(
                name="total_invoice_amount",
                label="Total Invoice Amount",
                description="Total amount to be paid",
                data_type="currency",
                required=True,
                validation_rules={"min_value": 0},
                extraction_hints="Final total amount, cannot be zero or empty"
            ),
            FieldDefinition(
                name="sales_tax_amount",
                label="Sales Tax Amount",
                description="Amount of sales tax charged",
                data_type="currency",
                required=False,
                extraction_hints="May be labeled as GST, VAT, Sales Tax, or Tax Amount"
            ),
            FieldDefinition(
                name="currency",
                label="Currency",
                description="Currency of the invoice amounts",
                data_type="text",
                required=False,
                default_value="PKR",
                extraction_hints="If not found, default to PKR"
            ),
            FieldDefinition(
                name="po_numbers",
                label="PO Numbers",
                description="Purchase Order numbers referenced in the invoice",
                data_type="array",
                required=False,
                validation_rules={"item_type": "number"},
                extraction_hints="Must be numeric values with proper PO labels"
            ),
            FieldDefinition(
                name="delivery_challan_number",
                label="Delivery Challan Number",
                description="Delivery challan or delivery order number",
                data_type="text",
                required=False,
                extraction_hints="Look for DCN, Delivery Order, or Challan Number - not Gate Pass"
            ),
            FieldDefinition(
                name="hs_code",
                label="HS Code",
                description="Harmonized System commodity classification code",
                data_type="text",
                required=False,
                extraction_hints="Usually numeric code for product classification"
            ),
            FieldDefinition(
                name="ntn_number",
                label="NTN Number",
                description="National Tax Number",
                data_type="text",
                required=False,
                extraction_hints="Tax identification number"
            )
        ]
        
        for field in default_fields:
            self.fields[field.name] = field
        
        # Default presets
        self.presets = {
            "Commercial Invoice": ["invoice_type", "invoice_number", "buyer_name", "supplier_name", 
                                 "invoice_date", "total_invoice_amount", "currency", "po_numbers"],
            "Sales Tax Invoice": ["invoice_type", "invoice_number", "buyer_name", "supplier_name", 
                                "invoice_date", "total_invoice_amount", "sales_tax_amount", 
                                "currency", "ntn_number"],
            "Full Pakistani Invoice": list(self.fields.keys())
        }
        
        self.save_config()
    
    def add_field(self, field: FieldDefinition):
        """Add or update a field definition"""
        self.fields[field.name] = field
        self.save_config()
    
    def remove_field(self, field_name: str):
        """Remove a field definition"""
        if field_name in self.fields:
            del self.fields[field_name]
            # Remove from presets
            for preset_fields in self.presets.values():
                if field_name in preset_fields:
                    preset_fields.remove(field_name)
            self.save_config()
    
    def get_field(self, field_name: str) -> FieldDefinition:
        """Get a field definition"""
        return self.fields.get(field_name)
    
    def get_all_fields(self) -> Dict[str, FieldDefinition]:
        """Get all field definitions"""
        return self.fields.copy()
    
    def add_preset(self, name: str, field_names: List[str]):
        """Add a field preset"""
        # Validate all field names exist
        valid_fields = [name for name in field_names if name in self.fields]
        self.presets[name] = valid_fields
        self.save_config()
    
    def remove_preset(self, name: str):
        """Remove a field preset"""
        if name in self.presets:
            del self.presets[name]
            self.save_config()
    
    def get_preset(self, name: str) -> List[str]:
        """Get field names for a preset"""
        return self.presets.get(name, [])
    
    def get_all_presets(self) -> Dict[str, List[str]]:
        """Get all presets"""
        return self.presets.copy()
    
    def get_active_fields(self, field_names: List[str] = None) -> Dict[str, FieldDefinition]:
        """Get only the specified fields, or all if none specified"""
        if field_names is None:
            return self.fields.copy()
        
        return {name: self.fields[name] for name in field_names if name in self.fields}
    
    def generate_extraction_prompt(self, field_names: List[str] = None) -> str:
        """Generate AI prompt for field extraction"""
        active_fields = self.get_active_fields(field_names)
        
        if not active_fields:
            return ""
        
        prompt = """You are an expert in finance and text extraction. Analyze the provided image and determine if it is an invoice.
An invoice must include clear payment/total payment amount. If the image contains this and can be identified as an invoice,
extract every label and its corresponding value. Format the output as JSON.

Fields to extract (Nothing Else):
"""
        
        for i, (name, field) in enumerate(active_fields.items(), 1):
            prompt += f"    {i}. {name} ({field.description}"
            if field.required:
                prompt += " - REQUIRED"
            if field.default_value:
                prompt += f" - defaults to {field.default_value}"
            if field.validation_rules:
                if field.data_type == "date" and "format" in field.validation_rules:
                    prompt += f" - format: {field.validation_rules['format']}"
                elif field.data_type == "array" and "item_type" in field.validation_rules:
                    prompt += f" - array of {field.validation_rules['item_type']}s only"
            prompt += ")\n"
        
        prompt += """
Guard Rails:
"""
        
        for name, field in active_fields.items():
            if field.extraction_hints:
                prompt += f"    - {field.label}: {field.extraction_hints}\n"
            
            if field.validation_rules:
                if "min_value" in field.validation_rules:
                    prompt += f"    - {field.label} cannot be empty or zero\n"
                if "format" in field.validation_rules:
                    prompt += f"    - {field.label} must be in {field.validation_rules['format']} format\n"
        
        prompt += """    - Convert Urdu text to English
    - Use proper labels for field identification
    
Return as JSON array: [{"field_name": "value", ...}]
"""
        
        return prompt
    
    def generate_verification_prompt(self, field_names: List[str] = None) -> str:
        """Generate AI prompt for field verification"""
        active_fields = self.get_active_fields(field_names)
        
        prompt = """You are a financial-OCR validator. Below is the JSON extracted from the document plus the image itself.
Check every field against the images and fix any mistakes or fill in missing values.

Validation Rules:
"""
        
        for name, field in active_fields.items():
            if field.required:
                prompt += f"- {field.label} cannot be empty\n"
            if field.default_value:
                prompt += f"- {field.label} defaults to {field.default_value} if not found\n"
            if field.extraction_hints:
                prompt += f"- {field.label}: {field.extraction_hints}\n"
                
            if field.validation_rules:
                if "format" in field.validation_rules:
                    prompt += f"- {field.label} format: {field.validation_rules['format']}\n"
                if "min_value" in field.validation_rules:
                    prompt += f"- {field.label} cannot be zero or negative\n"
                if field.data_type == "array" and "item_type" in field.validation_rules:
                    prompt += f"- {field.label} must be array of {field.validation_rules['item_type']}s\n"
        
        prompt += """- Convert Urdu to English

Return corrected JSON in same format.
"""
        
        return prompt

# Global instance
field_manager = FieldConfigManager()