# PDF to Presentation Converter

Transform medical PDFs into professional presentations using AI-powered content analysis and generation.

## 🚀 Features

- **AI-Powered Analysis**: Intelligent extraction and structuring of medical content
- **Multi-language Support**: Translate presentations to Turkish and other languages
- **Image Preservation**: Maintains images and diagrams from original PDFs
- **Professional Formatting**: Clean, medical presentation templates
- **Medical Translation**: Proper medical terminology translation
- **Modern UI**: Beautiful Streamlit-based user interface

## 📋 Requirements

- Python 3.8+
- Azure OpenAI API access
- Azure Translator API access (optional, for translation features)

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd PDF_to_Presentation
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   Create a `.env` file in the project root with the following variables:
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

## 🎯 Usage

1. **Start the application**:
   ```bash
   streamlit run app.py
   ```

2. **Open your browser** and navigate to the provided URL (usually `http://localhost:8501`)

3. **Upload a PDF** file using the file uploader

4. **Configure options** in the sidebar:
   - Select target language for translation
   - Choose processing options
   - Set custom presentation title

5. **Click "Convert to Presentation"** to start the conversion process

6. **Download** your generated PowerPoint presentation

## 🔧 How It Works

### 1. PDF Processing
- Extracts text and images from PDF using PyMuPDF
- Preserves document structure and formatting
- Handles complex medical documents with diagrams

### 2. AI Content Analysis
- Uses Azure OpenAI to analyze medical content
- Identifies key topics, concepts, and learning objectives
- Structures content for optimal presentation flow

### 3. Slide Generation
- Creates professional presentation slides
- Organizes content with proper medical terminology
- Includes images and diagrams from original PDF

### 4. Translation (Optional)
- Translates content to target language using Azure Translator
- Maintains medical terminology accuracy
- Translates image descriptions and captions

### 5. Presentation Assembly
- Generates PowerPoint (.pptx) file using python-pptx
- Applies professional medical presentation templates
- Includes proper formatting and styling

## 📁 Project Structure

```
PDF_to_Presentation/
├── app.py                 # Main Streamlit application
├── main_processor.py      # Orchestrator for the conversion process
├── pdf_processor.py       # PDF text and image extraction
├── llm_agent.py          # AI content analysis and slide generation
├── translation_service.py # Translation functionality
├── presentation_builder.py # PowerPoint creation
├── config.py             # Configuration and environment setup
├── requirements.txt      # Python dependencies
├── example/              # Example input/output files
│   ├── robbins-basic-pathology-10thpdf_compress-pages.pdf
│   └── AKUT İNFLAMASYONUN MORFOLJiK PATERNLERİ.pptx
└── output/               # Generated presentations (created automatically)
```

## 🎨 UI Features

- **Modern Interface**: Clean, professional design with medical theme
- **Real-time Progress**: Visual progress indicators during processing
- **File Validation**: Automatic validation of uploaded PDFs
- **Status Monitoring**: System status and configuration validation
- **Download Integration**: Direct download of generated presentations

## 🔍 Example

The `example/` folder contains:
- **Input**: `robbins-basic-pathology-10thpdf_compress-pages.pdf` - Medical pathology textbook
- **Output**: `AKUT İNFLAMASYONUN MORFOLJiK PATERNLERİ.pptx` - Generated Turkish presentation

## 🚨 Troubleshooting

### Common Issues

1. **Azure OpenAI not configured**:
   - Ensure all Azure OpenAI environment variables are set
   - Verify your API key and endpoint are correct

2. **Translation not working**:
   - Check Azure Translator configuration
   - Verify region and endpoint settings

3. **PDF processing errors**:
   - Ensure PDF is not password-protected
   - Check file size (recommended < 50MB)
   - Verify PDF is not corrupted

4. **Memory issues**:
   - Process smaller PDFs
   - Close other applications to free memory

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Azure OpenAI for AI capabilities
- Azure Translator for translation services
- Streamlit for the web interface
- PyMuPDF for PDF processing
- python-pptx for PowerPoint generation
