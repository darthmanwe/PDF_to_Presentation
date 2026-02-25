#!/usr/bin/env python3
"""
Test script to verify PDF to Presentation Converter setup
"""

import sys
import os

def test_imports():
    """Test if all required packages can be imported"""
    print("Testing package imports...")
    
    try:
        import streamlit
        print("✅ Streamlit imported successfully")
    except ImportError as e:
        print(f"❌ Streamlit import failed: {e}")
        return False
    
    try:
        import fitz  # PyMuPDF
        print("✅ PyMuPDF imported successfully")
    except ImportError as e:
        print(f"❌ PyMuPDF import failed: {e}")
        return False
    
    try:
        from pptx import Presentation
        print("✅ python-pptx imported successfully")
    except ImportError as e:
        print(f"❌ python-pptx import failed: {e}")
        return False
    
    try:
        from PIL import Image
        print("✅ Pillow imported successfully")
    except ImportError as e:
        print(f"❌ Pillow import failed: {e}")
        return False
    
    try:
        from openai import AzureOpenAI
        print("✅ OpenAI imported successfully")
    except ImportError as e:
        print(f"❌ OpenAI import failed: {e}")
        return False
    
    try:
        import requests
        print("✅ Requests imported successfully")
    except ImportError as e:
        print(f"❌ Requests import failed: {e}")
        return False
    
    try:
        from dotenv import load_dotenv
        print("✅ python-dotenv imported successfully")
    except ImportError as e:
        print(f"❌ python-dotenv import failed: {e}")
        return False
    
    return True

def test_local_imports():
    """Test if local modules can be imported"""
    print("\nTesting local module imports...")
    
    try:
        from config import get_azure_openai_client, AZURE_DEPLOYMENT_NAME
        print("✅ Config module imported successfully")
    except ImportError as e:
        print(f"❌ Config module import failed: {e}")
        return False
    
    try:
        from pdf_processor import PDFProcessor
        print("✅ PDF processor imported successfully")
    except ImportError as e:
        print(f"❌ PDF processor import failed: {e}")
        return False
    
    try:
        from llm_agent import LLMAgent
        print("✅ LLM agent imported successfully")
    except ImportError as e:
        print(f"❌ LLM agent import failed: {e}")
        return False
    
    try:
        from translation_service import TranslationService
        print("✅ Translation service imported successfully")
    except ImportError as e:
        print(f"❌ Translation service import failed: {e}")
        return False
    
    try:
        from presentation_builder import PresentationBuilder
        print("✅ Presentation builder imported successfully")
    except ImportError as e:
        print(f"❌ Presentation builder import failed: {e}")
        return False
    
    try:
        from main_processor import PDFToPresentationProcessor
        print("✅ Main processor imported successfully")
    except ImportError as e:
        print(f"❌ Main processor import failed: {e}")
        return False
    
    return True

def test_environment():
    """Test environment configuration"""
    print("\nTesting environment configuration...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check Azure OpenAI configuration
    azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OAI_KEY")
    deployment_name = os.getenv("AZURE_DEPLOYMENT_NAME")
    
    if azure_endpoint:
        print("✅ Azure OpenAI endpoint configured")
    else:
        print("⚠️ Azure OpenAI endpoint not configured")
    
    if azure_key:
        print("✅ Azure OpenAI key configured")
    else:
        print("⚠️ Azure OpenAI key not configured")
    
    if deployment_name:
        print("✅ Azure deployment name configured")
    else:
        print("⚠️ Azure deployment name not configured")
    
    # Check Azure Translator configuration
    translator_endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT")
    translator_key = os.getenv("AZURE_TRANSLATOR_KEY")
    translator_region = os.getenv("AZURE_TRANSLATOR_REGION")
    
    if translator_endpoint and translator_key and translator_region:
        print("✅ Azure Translator fully configured")
    else:
        print("⚠️ Azure Translator not fully configured (translation features will be limited)")
    
    return True

def test_file_structure():
    """Test if required files exist"""
    print("\nTesting file structure...")
    
    required_files = [
        "app.py",
        "main_processor.py",
        "pdf_processor.py",
        "llm_agent.py",
        "translation_service.py",
        "presentation_builder.py",
        "config.py",
        "requirements.txt"
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} missing")
            return False
    
    return True

def main():
    """Run all tests"""
    print("🧪 PDF to Presentation Converter - Setup Test")
    print("=" * 50)
    
    all_tests_passed = True
    
    # Test package imports
    if not test_imports():
        all_tests_passed = False
    
    # Test local imports
    if not test_local_imports():
        all_tests_passed = False
    
    # Test environment
    test_environment()
    
    # Test file structure
    if not test_file_structure():
        all_tests_passed = False
    
    print("\n" + "=" * 50)
    if all_tests_passed:
        print("🎉 All tests passed! Your setup is ready.")
        print("\nTo start the application, run:")
        print("streamlit run app.py")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        print("\nTo install missing dependencies, run:")
        print("pip install -r requirements.txt")
    
    return all_tests_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
