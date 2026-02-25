# Quick Setup Guide

## 🚀 Get Started in 3 Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file in the project root:
```env
# Azure OpenAI Configuration
AZURE_OAI_ENDPOINT=your_azure_openai_endpoint_here
AZURE_OAI_KEY=your_azure_openai_key_here
AZURE_DEPLOYMENT_NAME=your_deployment_name_here

# Azure Translator Configuration (optional)
AZURE_TRANSLATOR_ENDPOINT=your_azure_translator_endpoint_here
AZURE_TRANSLATOR_KEY=your_azure_translator_key_here
AZURE_TRANSLATOR_REGION=your_azure_translator_region_here
```

### 3. Run the Application

**Windows:**
```bash
run_app.bat
```

**Mac/Linux:**
```bash
./run_app.sh
```

**Manual:**
```bash
streamlit run app.py
```

## 🧪 Test Your Setup
```bash
python test_setup.py
```

## 📖 What You Get

- **Modern Web UI**: Beautiful Streamlit interface
- **PDF Processing**: Extract text and images from medical PDFs
- **AI Analysis**: Intelligent content structuring using Azure OpenAI
- **Translation**: Convert to Turkish and other languages
- **Presentation Generation**: Professional PowerPoint output

## 🎯 Example Workflow

1. Upload `example/robbins-basic-pathology-10thpdf_compress-pages.pdf`
2. Select "Turkish" for translation
3. Click "Convert to Presentation"
4. Download your generated `.pptx` file

## 🆘 Need Help?

- Check the main README.md for detailed documentation
- Run `python test_setup.py` to diagnose issues
- Ensure all environment variables are set correctly
