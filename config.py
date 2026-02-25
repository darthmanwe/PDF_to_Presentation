import os
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

# Azure OpenAI Configuration
def get_azure_openai_client():
    """Initialize and return Azure OpenAI client"""
    client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OAI_KEY"),
        api_version="2024-02-15-preview",
    )
    return client

# Get the Azure deployment name from the environment variable
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")

# Azure Translator Configuration
AZURE_TRANSLATOR_ENDPOINT = os.getenv("AZURE_TRANSLATOR_ENDPOINT")
AZURE_TRANSLATOR_KEY = os.getenv("AZURE_TRANSLATOR_KEY")
AZURE_TRANSLATOR_REGION = os.getenv("AZURE_TRANSLATOR_REGION")

# Supported languages
SUPPORTED_LANGUAGES = {
    "Turkish": "tr",
    "English": "en"
}
