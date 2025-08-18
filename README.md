# 📄 Invoice OCR Demo

A sophisticated AI-powered invoice processing system built with Streamlit and Google Gemini 2.0 Flash API. This application demonstrates advanced OCR capabilities for automated invoice data extraction and processing.

## 🚀 Features

- **Multi-format Support**: Process PDF, JPG, and PNG invoice files
- **Dynamic Field Configuration**: Add, remove, and customize extraction fields for any invoice type
- **Smart AI Extraction**: Extract custom-defined fields automatically using AI
- **Field Presets**: Pre-configured field sets for common invoice types
- **Ambiguity Detection**: Identify and resolve uncertain OCR results
- **Export Options**: Export data to Excel (summary) and JSON (detailed)
- **Review Interface**: Manual verification and correction capabilities
- **Import/Export Config**: Save and share field configurations across projects
- **Portfolio Ready**: Clean, professional UI suitable for demonstrations

## 🛠️ Technology Stack

- **Frontend**: Streamlit with custom CSS styling
- **AI/ML**: Google Gemini 2.0 Flash API for OCR
- **Data Processing**: Pandas for data manipulation
- **Image Processing**: PIL, pdf2image for format conversion
- **Export**: Excel and JSON export capabilities

## 📋 Default Extracted Fields

The system comes with 12 pre-configured fields optimized for Pakistani invoices:

1. **Invoice Type** (Commercial/Sales Tax)
2. **Invoice Number**
3. **Buyer Name**
4. **Supplier Name**
5. **Invoice Date** (DD-MM-YYYY format)
6. **Total Invoice Amount**
7. **Sales Tax Amount**
8. **Currency** (defaults to PKR)
9. **PO Numbers** (numeric only)
10. **Delivery Challan Number**
11. **HS Code**
12. **NTN Number**

### ⚙️ Custom Field Configuration

Users can now:
- **Add Custom Fields**: Define new fields with descriptions, data types, and validation rules
- **Create Field Presets**: Save field combinations for different invoice types
- **Configure Validation**: Set required fields, default values, and data type constraints
- **AI Extraction Hints**: Provide specific guidance to improve AI accuracy
- **Import/Export**: Share configurations across different deployments

## 🔧 Installation & Setup

### Prerequisites
- Python 3.9+
- uv package manager

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd invoice_ocr
   ```

2. **Install dependencies using uv**
   ```bash
   uv sync
   ```

3. **Set up environment variables (optional)**
   ```bash
   # Create .env file with your Gemini API key
   echo "GEMINI_API_KEY=your_api_key_here" > .env
   ```

4. **Run the application**
   ```bash
   uv run streamlit run app.py
   ```

## 🎯 Usage

1. **Configure Fields** (Optional): Set up custom fields for your specific invoice types
2. **Select Field Preset**: Choose from pre-configured field sets or create custom selection
3. **Upload Invoices**: Drag and drop PDF/image files
4. **AI Processing**: Automatic extraction with progress indicators using your custom fields
5. **Review Mode**: Verify and correct extracted data
6. **Summary View**: Overview of all processed invoices
7. **Export Data**: Download Excel summaries or JSON details

### ⚙️ Field Configuration Workflow

1. **Access Field Config**: Click "⚙️ Configure Fields" button
2. **Manage Fields**: Add, edit, or delete extraction fields
3. **Create Presets**: Group fields for specific invoice types (e.g., "E-commerce Invoice", "Service Invoice")
4. **Set Validation**: Define required fields, data types, and extraction hints
5. **Export/Import**: Save configurations as JSON files for backup or sharing

## 🏗️ Architecture

```
app.py                 # Main Streamlit application
ocr_pipeline.py        # Core OCR processing pipeline
├── PDF to Image       # Convert PDFs to images
├── OCR Extraction     # Extract data using Gemini AI
├── Verification       # Validate and correct results
└── Enrichment         # Add ambiguity detection
```

## 🎨 UI Features

- **Gradient Headers**: Professional purple gradient styling
- **Progress Indicators**: Real-time processing feedback
- **Interactive Cards**: Clean information presentation
- **Responsive Design**: Works on different screen sizes
- **Export Buttons**: One-click data export functionality

## 🔐 Security & Privacy

- No data persistence (demo mode)
- Local file processing only
- API keys can be environment-configured
- No sensitive data logging

## 📊 Export Formats

### Excel Export (Summary View)
- All invoices in tabular format
- Perfect for accounting workflows
- Includes ambiguity flags

### JSON Export (Detailed View)
- Complete extracted data
- Includes confidence scores
- Machine-readable format

## 🤖 AI Processing Pipeline

1. **Document Classification**: Verify if image contains invoice
2. **Field Extraction**: Extract 12 key invoice fields
3. **Data Verification**: Validate and correct extracted data
4. **Ambiguity Detection**: Identify uncertain extractions
5. **Format Standardization**: Ensure consistent data formats

## 🌟 Demo Features

- **No Authentication**: Streamlined for portfolio demonstration
- **Sample Data**: Works with various invoice formats
- **Real-time Processing**: Live feedback during AI processing
- **Professional UI**: Portfolio-ready presentation

## 📞 Contact

**Developer**: Moeed  
**Website**: [meetmoeed.com](https://meetmoeed.com)  
**Project Type**: Portfolio Demonstration

## 📄 License

This is a portfolio demonstration project. For commercial use, please contact the developer.

---

*Built with ❤️ using Streamlit and Google Gemini AI*