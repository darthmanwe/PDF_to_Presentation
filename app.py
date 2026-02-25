import streamlit as st
import os
import tempfile
from datetime import datetime
from main_processor import PDFToPresentationProcessor
from config import SUPPORTED_LANGUAGES
import time

# Page configuration
st.set_page_config(
    page_title="PDF to Presentation Converter",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .upload-section {
        background-color: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        border: 2px dashed #dee2e6;
        text-align: center;
        margin: 2rem 0;
    }
    .success-message {
        background-color: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
    }
    .error-message {
        background-color: #f8d7da;
        color: #721c24;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
    }
    .info-box {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #bee5eb;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Header
    st.markdown('<h1 class="main-header">📊 PDF to Presentation Converter</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Transform medical PDFs into professional presentations with AI</p>', unsafe_allow_html=True)
    
    # Initialize session state
    if 'processor' not in st.session_state:
        st.session_state.processor = PDFToPresentationProcessor()
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Language selection
        st.subheader("Translation Options")
        target_language = st.selectbox(
            "Translate to:",
            ["English (Original)"] + list(SUPPORTED_LANGUAGES.keys()),
            help="Select target language for translation"
        )
        
        # Get language code
        if target_language == "English (Original)":
            target_language_code = None
        else:
            target_language_code = SUPPORTED_LANGUAGES[target_language]
        
        # Processing options
        st.subheader("Processing Options")
        text_only_mode = st.checkbox("Text-Only Operation", value=True, help="Extract only text and figure annotations, skip image processing")
        include_images = st.checkbox("Include images from PDF", value=True, disabled=text_only_mode)
        
        # Annotation extraction options (only shown in text-only mode)
        if text_only_mode:
            st.subheader("Annotation Extraction")
            extract_figure_annotations = st.checkbox("Extract Figure Annotations", value=False, help="Extract text starting with 'Figure X.X' at beginning of sentences")
            extract_table_annotations = st.checkbox("Extract Table Annotations", value=False, help="Extract text found in table frames and captions")
        else:
            extract_figure_annotations = False
            extract_table_annotations = False
        
        auto_title = st.checkbox("Auto-generate title from content", value=True)
        
        # Custom title input
        if not auto_title:
            custom_title = st.text_input("Custom presentation title:", "Medical Presentation")
        else:
            custom_title = None
        
        # Status information
        st.subheader("System Status")
        status = st.session_state.processor.get_processing_status()
        
        if status['pdf_loaded']:
            st.success("✅ PDF loaded")
        else:
            st.info("📄 No PDF loaded")
        
        if status['translation_available']:
            st.success("✅ Translation service available")
            
            # Show translation rate limit status
            try:
                rate_status = st.session_state.processor.translation_service.get_rate_limit_status()
                st.info(f"📊 Translation: {rate_status['chars_this_minute']:,}/{rate_status['max_chars_per_minute']:,} chars this minute")
            except:
                pass
        else:
            st.warning("⚠️ Translation service not configured")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📁 Upload PDF")
        
        # File upload
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=['pdf'],
            help="Upload a medical PDF document to convert to presentation"
        )
        
        if uploaded_file is not None:
            # Display file info
            file_details = {
                "Filename": uploaded_file.name,
                "File size": f"{uploaded_file.size / 1024:.2f} KB",
                "File type": uploaded_file.type
            }
            
            st.json(file_details)
            
            # Debug: Show what we're validating
            st.info(f"🔍 Validating file: {uploaded_file.name}")
            
            # Validate file
            validation = st.session_state.processor.validate_inputs(
                uploaded_file.name, 
                target_language_code
            )
            
            # Debug: Show validation results
            st.info(f"Validation result: {validation}")
            
            if not validation['valid']:
                for error in validation['errors']:
                    st.error(error)
                return
            
            if validation['warnings']:
                for warning in validation['warnings']:
                    st.warning(warning)
    
    with col2:
        st.header("🎯 Quick Actions")
        
        # Process button
        if uploaded_file is not None and not st.session_state.processing:
            if st.button("🚀 Convert to Presentation", type="primary", use_container_width=True):
                st.session_state.processing = True
                process_pdf(uploaded_file, target_language_code, custom_title, include_images, text_only_mode, extract_figure_annotations, extract_table_annotations)
        
        # Progress indicator
        if st.session_state.processing:
            with st.spinner("Processing PDF..."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Simulate progress
                for i in range(5):
                    progress_bar.progress((i + 1) * 20)
                    status_text.text(f"Step {i + 1}/5: Processing...")
                    time.sleep(0.5)
                
                progress_bar.progress(100)
                status_text.text("Complete!")
    
    # Information section
    st.markdown("---")
    st.header("ℹ️ How it works")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown("""
        ### 1. 📄 Upload
        Upload your medical PDF document
        """)
    
    with col2:
        st.markdown("""
        ### 2. 🔍 Analyze
        AI analyzes content and extracts key information
        """)
    
    with col3:
        st.markdown("""
        ### 3. 🎯 Generate
        Create structured presentation slides
        """)
    
    with col4:
        st.markdown("""
        ### 4. 🌐 Translate
        Optional translation to target language
        """)
    
    with col5:
        st.markdown("""
        ### 5. 📊 Export
        Download your PowerPoint presentation
        """)
    
    # Features section
    st.markdown("---")
    st.header("✨ Features")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        - **AI-Powered Analysis**: Intelligent content extraction and structuring
        - **Medical Focus**: Optimized for medical and educational content
        - **Image Support**: Preserves and includes images from original PDF
        - **Professional Formatting**: Clean, medical presentation templates
        """)
    
    with col2:
        st.markdown("""
        - **Multi-language Support**: Translate to Turkish and other languages
        - **Medical Translation**: Proper medical terminology translation
        - **Batch Processing**: Handle large documents efficiently
        - **Customizable Output**: Adjust titles, content, and formatting
        """)

def process_pdf(uploaded_file, target_language_code, custom_title, include_images, text_only_mode, extract_figure_annotations, extract_table_annotations):
    """Process the uploaded PDF file"""
    
    # Create a debug container to show processing steps
    debug_container = st.container()
    
    with debug_container:
        st.subheader("🔍 Debug Information")
        debug_text = st.empty()
    
    try:
        debug_text.text("Step 1: Creating temporary file...")
        
        # Create temporary file and ensure it's properly saved
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as tmp_file:
            # Write the uploaded file content to temporary file
            tmp_file.write(uploaded_file.getvalue())
            tmp_file.flush()  # Ensure data is written to disk
            tmp_pdf_path = tmp_file.name
        
        debug_text.text(f"Step 2: Temporary file created at: {tmp_pdf_path}")
        
        # Verify the file exists and is readable
        if not os.path.exists(tmp_pdf_path):
            debug_text.text(f"ERROR: Temporary file was not created: {tmp_pdf_path}")
            raise FileNotFoundError(f"Temporary file was not created: {tmp_pdf_path}")
        
        # Check file size to ensure it was written properly
        file_size = os.path.getsize(tmp_pdf_path)
        if file_size == 0:
            debug_text.text("ERROR: Temporary file is empty")
            raise ValueError("Temporary file is empty")
        
        debug_text.text(f"Step 3: File verified - Size: {file_size} bytes")
        
        # Create output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"presentation_{timestamp}.pptx"
        output_path = os.path.join("output", output_filename)
        
        # Ensure output directory exists
        os.makedirs("output", exist_ok=True)
        
        debug_text.text("Step 4: Starting PDF processing...")
        
        # Process the PDF
        processor = st.session_state.processor
        result_path = processor.process_pdf_to_presentation(
            pdf_path=tmp_pdf_path,
            output_path=output_path,
            target_language=target_language_code,
            pdf_title=custom_title,
            text_only_mode=text_only_mode,
            extract_figure_annotations=extract_figure_annotations,
            extract_table_annotations=extract_table_annotations
        )
        
        debug_text.text("Step 5: Processing completed successfully!")
        
        # Success message
        st.success("✅ Presentation created successfully!")
        
        # Download button
        with open(result_path, "rb") as file:
            st.download_button(
                label="📥 Download Presentation",
                data=file.read(),
                file_name=output_filename,
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True
            )
        
        # Display presentation info
        st.info(f"📊 Presentation saved as: {output_filename}")
        
    except Exception as e:
        debug_text.text(f"ERROR: {str(e)}")
        st.error(f"❌ Error processing PDF: {str(e)}")
        print(f"Error details: {e}")
        
        # Show more detailed error information
        st.error("🔍 Detailed Error Information:")
        st.code(f"""
Error Type: {type(e).__name__}
Error Message: {str(e)}
Current Directory: {os.getcwd()}
        """)
        
    finally:
        # Clean up temporary file
        try:
            if 'tmp_pdf_path' in locals() and os.path.exists(tmp_pdf_path):
                os.unlink(tmp_pdf_path)
                debug_text.text(f"Cleanup: Temporary file removed")
        except Exception as cleanup_error:
            debug_text.text(f"Warning: Could not clean up temporary file: {cleanup_error}")
        
        st.session_state.processing = False

if __name__ == "__main__":
    main()
