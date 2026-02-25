import PyPDF2
import fitz  # PyMuPDF
from PIL import Image
import io
import os
import streamlit as st
from typing import List, Dict, Tuple, Optional

class PDFProcessor:
    """Handles PDF text and image extraction"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.text_content = []
        self.images = []
        
    def extract_text_and_images(self) -> Dict:
        """Extract both text and images from PDF"""
        try:
            st.info(f"Opening PDF file: {self.pdf_path}")
            
            # Use PyMuPDF for better text and image extraction
            doc = fitz.open(self.pdf_path)
            st.success(f"PDF opened successfully. Total pages: {len(doc)}")
            
            extracted_content = {
                'pages': [],
                'total_pages': len(doc)
            }
            
            for page_num in range(len(doc)):
                st.info(f"Processing page {page_num + 1}/{len(doc)}")
                page = doc.load_page(page_num)
                
                # Extract text
                text = page.get_text()
                st.info(f"Page {page_num + 1}: Extracted {len(text)} characters of text")
                
                # Extract images
                image_list = page.get_images()
                st.info(f"Page {page_num + 1}: Found {len(image_list)} images")
                page_images = []
                
                for img_index, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        pix = fitz.Pixmap(doc, xref)
                        
                        if pix.n - pix.alpha < 4:  # GRAY or RGB
                            img_data = pix.tobytes("png")
                            page_images.append({
                                'index': img_index,
                                'data': img_data,
                                'format': 'png'
                            })
                        else:  # CMYK: convert to RGB first
                            pix1 = fitz.Pixmap(fitz.csRGB, pix)
                            img_data = pix1.tobytes("png")
                            page_images.append({
                                'index': img_index,
                                'data': img_data,
                                'format': 'png'
                            })
                            pix1 = None
                        pix = None
                        
                    except Exception as e:
                        st.error(f"Error extracting image {img_index} from page {page_num}: {e}")
                        continue
                
                extracted_content['pages'].append({
                    'page_number': page_num + 1,
                    'text': text,
                    'images': page_images
                })
            
            doc.close()
            st.success(f"PDF processing completed successfully")
            return extracted_content
            
        except Exception as e:
            st.error(f"Error in PDF processing: {e}")
            raise Exception(f"Error processing PDF: {e}")
    
    def get_page_summary(self, page_content: Dict) -> str:
        """Create a summary of page content for LLM processing"""
        summary = f"Page {page_content['page_number']}:\n"
        summary += f"Text length: {len(page_content['text'])} characters\n"
        summary += f"Number of images: {len(page_content['images'])}\n"
        
        # Add first 200 characters of text as preview
        text_preview = page_content['text'][:200].replace('\n', ' ')
        if len(page_content['text']) > 200:
            text_preview += "..."
        summary += f"Text preview: {text_preview}\n"
        
        return summary
    
    def save_image(self, image_data: bytes, output_path: str, format: str = 'png'):
        """Save extracted image to file"""
        try:
            with open(output_path, 'wb') as f:
                f.write(image_data)
            return output_path
        except Exception as e:
            raise Exception(f"Error saving image: {e}")
