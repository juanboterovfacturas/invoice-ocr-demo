import streamlit as st
import json
from typing import Dict, List
from field_manager import field_manager, FieldDefinition

def render_field_config_page():
    """Render the field configuration page"""
    
    st.markdown("""
    <div class="main-header">
        <h1>⚙️ Field Configuration</h1>
        <p style="font-size: 1.2rem; margin-bottom: 0;">
            Customize Invoice Fields for Any Document Type
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Tabs for different sections
    tab1, tab2, tab3 = st.tabs(["📋 Manage Fields", "🎯 Presets", "📤 Import/Export"])
    
    with tab1:
        render_field_management()
    
    with tab2:
        render_preset_management()
    
    with tab3:
        render_import_export()

def render_field_management():
    """Render field management interface"""
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Check if we're editing an existing field
        edit_field = st.session_state.get("edit_field", None)
        
        if edit_field:
            st.subheader(f"✏️ Editing: {edit_field.label}")
            if st.button("❌ Cancel Edit"):
                del st.session_state.edit_field
                st.rerun()
        else:
            st.subheader("📝 Add New Field")
        
        # Field form
        with st.form("field_form_main"):
            name = st.text_input("Field Name (lowercase_underscore)", 
                               value=edit_field.name if edit_field else "",
                               help="Internal name used in code (e.g., invoice_number)")
            label = st.text_input("Display Label", 
                                value=edit_field.label if edit_field else "",
                                help="User-friendly name (e.g., Invoice Number)")
            description = st.text_area("Description", 
                                     value=edit_field.description if edit_field else "",
                                     help="What this field represents")
            
            data_type_options = ["text", "number", "date", "currency", "array"]
            current_data_type_index = 0
            if edit_field and edit_field.data_type in data_type_options:
                current_data_type_index = data_type_options.index(edit_field.data_type)
            
            data_type = st.selectbox("Data Type", 
                                   data_type_options,
                                   index=current_data_type_index)
            
            required = st.checkbox("Required Field", value=edit_field.required if edit_field else False)
            default_value = st.text_input("Default Value (optional)", 
                                        value=edit_field.default_value if edit_field else "")
            extraction_hints = st.text_area("Extraction Hints", 
                                          value=edit_field.extraction_hints if edit_field else "",
                                          help="Additional guidance for AI extraction")
            
            # Validation rules based on data type
            validation_rules = {}
            if data_type == "date":
                default_format = "DD-MM-YYYY"
                if edit_field and edit_field.validation_rules and "format" in edit_field.validation_rules:
                    default_format = edit_field.validation_rules["format"]
                date_format = st.text_input("Date Format", value=default_format)
                if date_format:
                    validation_rules["format"] = date_format
            elif data_type == "currency" or data_type == "number":
                default_min = 0.0
                if edit_field and edit_field.validation_rules and "min_value" in edit_field.validation_rules:
                    default_min = float(edit_field.validation_rules["min_value"])
                min_value = st.number_input("Minimum Value", value=default_min, step=0.01)
                validation_rules["min_value"] = min_value
            elif data_type == "array":
                default_item_type = "text"
                if edit_field and edit_field.validation_rules and "item_type" in edit_field.validation_rules:
                    default_item_type = edit_field.validation_rules["item_type"]
                item_type_options = ["text", "number"]
                item_type_index = 0
                if default_item_type in item_type_options:
                    item_type_index = item_type_options.index(default_item_type)
                item_type = st.selectbox("Array Item Type", item_type_options, index=item_type_index)
                validation_rules["item_type"] = item_type
            
            submit_text = "Update Field" if edit_field else "Add Field"
            submitted = st.form_submit_button(submit_text)
            
            if submitted and name and label and description:
                field = FieldDefinition(
                    name=name.lower().replace(" ", "_"),
                    label=label,
                    description=description,
                    data_type=data_type,
                    required=required,
                    default_value=default_value,
                    validation_rules=validation_rules,
                    extraction_hints=extraction_hints
                )
                field_manager.add_field(field)
                # Clear the edit field from session state
                if "edit_field" in st.session_state:
                    del st.session_state.edit_field
                st.success(f"Field '{label}' added/updated successfully!")
                st.rerun()
    
    with col2:
        st.subheader("📊 Current Fields")
        
        all_fields = field_manager.get_all_fields()
        
        if not all_fields:
            st.info("No fields configured. Add your first field on the left.")
            return
        
        # Display fields in a table format
        for name, field in all_fields.items():
            with st.expander(f"{field.label} ({field.name})", expanded=False):
                col_info, col_actions = st.columns([3, 1])
                
                with col_info:
                    st.write(f"**Description:** {field.description}")
                    st.write(f"**Type:** {field.data_type}")
                    st.write(f"**Required:** {'Yes' if field.required else 'No'}")
                    if field.default_value:
                        st.write(f"**Default:** {field.default_value}")
                    if field.extraction_hints:
                        st.write(f"**Hints:** {field.extraction_hints}")
                    if field.validation_rules:
                        st.write(f"**Validation:** {field.validation_rules}")
                
                with col_actions:
                    if st.button(f"🗑️ Delete", key=f"delete_{name}"):
                        field_manager.remove_field(name)
                        st.success(f"Field '{field.label}' deleted!")
                        st.rerun()
                    
                    if st.button(f"✏️ Edit", key=f"edit_{name}"):
                        # Store field data in session state for editing
                        st.session_state.edit_field = field
                        st.success(f"'{field.label}' loaded for editing! Check the form on the left.")
                        st.rerun()

def render_preset_management():
    """Render preset management interface"""
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🎯 Create Preset")
        
        with st.form("preset_form_main"):
            preset_name = st.text_input("Preset Name", 
                                      placeholder="e.g., E-commerce Invoice")
            
            all_fields = field_manager.get_all_fields()
            if all_fields:
                selected_fields = st.multiselect(
                    "Select Fields",
                    options=list(all_fields.keys()),
                    format_func=lambda x: f"{all_fields[x].label} ({x})"
                )
            else:
                selected_fields = []
                st.warning("No fields available. Create fields first in the Manage Fields tab.")
            
            submitted = st.form_submit_button("Create Preset")
            
            if submitted and preset_name and selected_fields:
                field_manager.add_preset(preset_name, selected_fields)
                st.success(f"Preset '{preset_name}' created successfully!")
                st.rerun()
    
    with col2:
        st.subheader("📋 Current Presets")
        
        all_presets = field_manager.get_all_presets()
        all_fields = field_manager.get_all_fields()
        
        if not all_presets:
            st.info("No presets configured. Create your first preset on the left.")
            return
        
        for preset_name, field_names in all_presets.items():
            with st.expander(f"{preset_name} ({len(field_names)} fields)", expanded=False):
                col_info, col_actions = st.columns([3, 1])
                
                with col_info:
                    st.write("**Fields included:**")
                    for field_name in field_names:
                        if field_name in all_fields:
                            field = all_fields[field_name]
                            required_badge = "🔴" if field.required else "⚪"
                            st.write(f"{required_badge} {field.label} ({field_name})")
                        else:
                            st.write(f"❌ {field_name} (field not found)")
                
                with col_actions:
                    if st.button(f"🗑️ Delete", key=f"delete_preset_{preset_name}"):
                        field_manager.remove_preset(preset_name)
                        st.success(f"Preset '{preset_name}' deleted!")
                        st.rerun()
                    
                    if st.button(f"📋 Use Preset", key=f"use_preset_{preset_name}"):
                        st.session_state.selected_preset = preset_name
                        st.session_state.active_fields = field_names
                        st.success(f"Preset '{preset_name}' activated!")
                        st.info("Return to the main app to process invoices with this preset.")

def render_import_export():
    """Render import/export interface"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📤 Export Configuration")
        
        if st.button("📥 Download Current Config"):
            all_fields = field_manager.get_all_fields()
            all_presets = field_manager.get_all_presets()
            
            config_data = {
                'fields': [
                    {
                        'name': field.name,
                        'label': field.label,
                        'description': field.description,
                        'data_type': field.data_type,
                        'required': field.required,
                        'default_value': field.default_value,
                        'validation_rules': field.validation_rules,
                        'extraction_hints': field.extraction_hints
                    }
                    for field in all_fields.values()
                ],
                'presets': all_presets
            }
            
            config_json = json.dumps(config_data, indent=2, ensure_ascii=False)
            
            st.download_button(
                label="⬇️ Download field_config.json",
                data=config_json,
                file_name="field_config.json",
                mime="application/json"
            )
    
    with col2:
        st.subheader("📥 Import Configuration")
        
        uploaded_config = st.file_uploader(
            "Upload field_config.json",
            type=['json'],
            help="Upload a previously exported field configuration"
        )
        
        if uploaded_config is not None:
            try:
                config_data = json.load(uploaded_config)
                
                # Preview what will be imported
                st.subheader("Preview Import")
                
                if 'fields' in config_data:
                    st.write(f"**Fields to import:** {len(config_data['fields'])}")
                    with st.expander("Field Details"):
                        for field_data in config_data['fields']:
                            st.write(f"- {field_data.get('label', 'N/A')} ({field_data.get('name', 'N/A')})")
                
                if 'presets' in config_data:
                    st.write(f"**Presets to import:** {len(config_data['presets'])}")
                    with st.expander("Preset Details"):
                        for preset_name, field_names in config_data['presets'].items():
                            st.write(f"- {preset_name}: {len(field_names)} fields")
                
                col_import, col_merge = st.columns(2)
                
                with col_import:
                    if st.button("🔄 Replace All", type="primary"):
                        import_config(config_data, replace=True)
                        st.success("Configuration replaced successfully!")
                        st.rerun()
                
                with col_merge:
                    if st.button("➕ Merge Config"):
                        import_config(config_data, replace=False)
                        st.success("Configuration merged successfully!")
                        st.rerun()
                
            except Exception as e:
                st.error(f"Error reading config file: {e}")

def import_config(config_data: Dict, replace: bool = False):
    """Import configuration data"""
    
    if replace:
        # Clear existing configuration
        field_manager.fields.clear()
        field_manager.presets.clear()
    
    # Import fields
    if 'fields' in config_data:
        for field_data in config_data['fields']:
            try:
                field = FieldDefinition(
                    name=field_data.get('name', ''),
                    label=field_data.get('label', ''),
                    description=field_data.get('description', ''),
                    data_type=field_data.get('data_type', 'text'),
                    required=field_data.get('required', False),
                    default_value=field_data.get('default_value', ''),
                    validation_rules=field_data.get('validation_rules', {}),
                    extraction_hints=field_data.get('extraction_hints', '')
                )
                field_manager.add_field(field)
            except Exception as e:
                st.warning(f"Failed to import field: {field_data.get('name', 'unknown')} - {e}")
    
    # Import presets
    if 'presets' in config_data:
        for preset_name, field_names in config_data['presets'].items():
            field_manager.add_preset(preset_name, field_names)
    
    field_manager.save_config()

def get_preset_selector():
    """Render preset selector for main app"""
    all_presets = field_manager.get_all_presets()
    
    if not all_presets:
        st.warning("No presets configured. Configure fields and presets first.")
        return None
    
    preset_options = ["Custom Selection"] + list(all_presets.keys())
    selected_preset = st.selectbox(
        "Select Field Preset",
        options=preset_options,
        index=0 if "selected_preset" not in st.session_state else preset_options.index(st.session_state.get("selected_preset", preset_options[0])),
        help="Choose a predefined set of fields or create custom selection"
    )
    
    if selected_preset == "Custom Selection":
        all_fields = field_manager.get_all_fields()
        if all_fields:
            selected_fields = st.multiselect(
                "Select Fields to Extract",
                options=list(all_fields.keys()),
                default=st.session_state.get("active_fields", list(all_fields.keys())[:5]),
                format_func=lambda x: f"{all_fields[x].label} ({'Required' if all_fields[x].required else 'Optional'})"
            )
            return selected_fields
        else:
            st.error("No fields configured!")
            return None
    else:
        return field_manager.get_preset(selected_preset)

# Helper function to get field manager instance
def get_field_manager():
    return field_manager