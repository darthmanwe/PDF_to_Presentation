import os
import tempfile
import streamlit as st
from typing import Dict, Any, Optional, List
from pdf_processor import PDFProcessor
from llm_agent import LLMAgent
from translation_service import TranslationService
from presentation_builder import PresentationBuilder
from config import SUPPORTED_LANGUAGES

class PDFToPresentationProcessor:
    """Main orchestrator for PDF to detailed presentation conversion"""
    
    def __init__(self):
        self.pdf_processor = None
        self.llm_agent = LLMAgent()
        self.translation_service = TranslationService()
        self.presentation_builder = PresentationBuilder()
        self.temp_dir = None
    
    def process_pdf_to_presentation(self, 
                                  pdf_path: str, 
                                  output_path: str,
                                  target_language: Optional[str] = None,
                                  pdf_title: Optional[str] = None,
                                  text_only_mode: bool = False,
                                  extract_figure_annotations: bool = False,
                                  extract_table_annotations: bool = False) -> str:
        """Main method to convert PDF to detailed presentation"""
        
        try:
            # Step 1: Extract content from PDF
            st.write("Step 1: Extracting detailed content from PDF...")
            pdf_content = self._extract_pdf_content(pdf_path)
            
            # Step 2: Create image slides or annotation slides based on mode
            if text_only_mode:
                st.write("Step 2: Extracting figure and table annotations (text-only mode)...")
                image_slides = self._create_annotation_slides_from_pdf(
                    pdf_content, 
                    extract_figure_annotations, 
                    extract_table_annotations
                )
            else:
                st.write("Step 2: Creating image slides from PDF images...")
                image_slides = self._create_image_slides_from_pdf(pdf_content)
            
            # Step 3: Analyze content using LLM for detailed information
            st.write("Step 3: Analyzing content for detailed medical information...")
            analyzed_content = self.llm_agent.analyze_pdf_content(pdf_content)

            # Step 4: Generate detailed slides in English
            st.write("Step 4: Generating detailed presentation slides...")
            text_slides_data = self.llm_agent.generate_slides(analyzed_content)
            
            print(f"🔍 DEBUG: Generated {len(text_slides_data)} text slides")
            for i, slide in enumerate(text_slides_data):
                print(f"🔍 DEBUG: Text slide {i+1}: '{slide.get('title', 'NO TITLE')}' - {len(slide.get('content', []))} paragraphs")
            
            # Step 5: Combine text slides with image slides
            st.write("Step 5: Combining text and image slides...")
            combined_slides = self._combine_text_and_image_slides(text_slides_data, image_slides)
            
            print(f"🔍 DEBUG: Combined {len(combined_slides)} total slides")
            for i, slide in enumerate(combined_slides):
                print(f"🔍 DEBUG: Combined slide {i+1}: '{slide.get('title', 'NO TITLE')}' - Type: {slide.get('slide_type', 'NO TYPE')}")
            
            # Step 6: Translate content if needed
            if target_language and target_language != "en":
                st.write(f"Step 6: Translating content to {target_language}...")
                combined_slides = self._translate_detailed_slides(combined_slides, target_language)
            
            # Step 7: Create detailed presentation with images
            st.write("Step 7: Building detailed presentation...")
            print(f"🔍 DEBUG: Final slides data before presentation creation: {len(combined_slides)} slides")
            
            # Debug the first few slides
            for i, slide in enumerate(combined_slides[:3]):
                print(f"🔍 DEBUG: Slide {i+1} data:")
                print(f"  - Title: '{slide.get('title', 'NO TITLE')}'")
                print(f"  - Type: '{slide.get('slide_type', 'NO TYPE')}'")
                print(f"  - Content count: {len(slide.get('content', []))}")
                if slide.get('content'):
                    print(f"  - First content: '{slide['content'][0][:100]}...'")
            
            final_output_path = self._create_detailed_presentation(
                combined_slides,
                output_path,
                pdf_title or os.path.basename(pdf_path),
                pdf_content  # Pass PDF content for image handling
            )
            
            st.write(f"Detailed presentation created successfully: {final_output_path}")
            return final_output_path
            
        except Exception as e:
            raise Exception(f"PDF to detailed presentation conversion failed: {e}")
        finally:
            self._cleanup_temp_files()
    
    def _extract_pdf_content(self, pdf_path: str) -> Dict[str, Any]:
        """Extract text and images from PDF"""
        st.write(f"🔍 Attempting to extract detailed content from: {pdf_path}")
        
        if not os.path.exists(pdf_path):
            st.error(f"❌ File does not exist at path: {pdf_path}")
            st.write(f"Current working directory: {os.getcwd()}")
            st.write(f"Directory contents: {os.listdir('.')}")
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Check if file is readable
        if not os.access(pdf_path, os.R_OK):
            st.error(f"❌ File exists but is not readable: {pdf_path}")
            raise PermissionError(f"Cannot read PDF file: {pdf_path}")
        
        # Check file size
        file_size = os.path.getsize(pdf_path)
        st.write(f"📄 PDF file size: {file_size} bytes")
        
        if file_size == 0:
            st.error(f"❌ PDF file is empty: {pdf_path}")
            raise ValueError(f"PDF file is empty: {pdf_path}")
        
        try:
            st.write("🔄 Initializing PDF processor...")
            self.pdf_processor = PDFProcessor(pdf_path)
            st.write("📖 Extracting detailed content from PDF...")
            content = self.pdf_processor.extract_text_and_images()
            st.success("✅ Successfully extracted detailed content from PDF")
            return content
        except Exception as e:
            st.error(f"❌ Error during PDF processing: {e}")
            raise Exception(f"Failed to extract content from PDF: {e}")
    
    def _create_image_slides_from_pdf(self, pdf_content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create image slides directly from PDF images without LLM"""
        image_slides = []
        
        for page in pdf_content.get('pages', []):
            page_num = page['page_number']
            images = page.get('images', [])
            page_text = page.get('text', '')
            
            if images:
                # Extract figure captions from page text
                figure_captions = self._extract_figure_captions(page_text)
                
                # Split images into groups of 2 per slide
                images_per_slide = 2
                for i in range(0, len(images), images_per_slide):
                    image_group = images[i:i + images_per_slide]
                    
                    # Create a slide for this group of images
                    image_slide = {
                        'title': f'Figures from Page {page_num}',
                        'content': [],  # No bullet points
                        'slide_type': 'image',
                        'image_descriptions': [],
                        'page_images': [],
                        'page_number': page_num,
                        'is_image_slide': True
                    }
                    
                    for j, img_data in enumerate(image_group):
                        # Add image data
                        image_slide['page_images'].append({
                            'index': i + j,
                            'data': img_data['data'],
                            'format': img_data['format']
                        })
                        
                        # Use extracted caption or fallback
                        caption_index = i + j
                        if caption_index < len(figure_captions):
                            caption = figure_captions[caption_index]
                        else:
                            caption = f"Figure from page {page_num}"
                        
                        image_slide['image_descriptions'].append(caption)
                    
                    image_slides.append(image_slide)
        
        print(f"Created {len(image_slides)} image slides from PDF")
        return image_slides
    
    def _create_annotation_slides_from_pdf(self, pdf_content: Dict[str, Any], 
                                         extract_figure_annotations: bool = False,
                                         extract_table_annotations: bool = False) -> List[Dict[str, Any]]:
        """Create annotation slides from figure/table captions in text-only mode"""
        annotation_slides = []
        
        for page in pdf_content.get('pages', []):
            page_num = page['page_number']
            page_text = page.get('text', '')
            
            # Extract annotations based on user preferences
            all_annotations = []
            
            if extract_figure_annotations:
                figure_annotations = self._extract_figure_annotations(page_text)
                all_annotations.extend(figure_annotations)
            
            if extract_table_annotations:
                table_annotations = self._extract_table_annotations(page_text)
                all_annotations.extend(table_annotations)
            
            if all_annotations:
                # Split annotations into groups of 2 per slide
                annotations_per_slide = 2
                for i in range(0, len(all_annotations), annotations_per_slide):
                    annotation_group = all_annotations[i:i + annotations_per_slide]
                    
                    # Create a slide for this group of annotations
                    annotation_slide = {
                        'title': f'Figures and Tables from Page {page_num}',
                        'content': [],  # No bullet points
                        'slide_type': 'annotation',
                        'annotation_descriptions': annotation_group,
                        'page_number': page_num,
                        'is_annotation_slide': True
                    }
                    
                    annotation_slides.append(annotation_slide)
        
        print(f"Created {len(annotation_slides)} annotation slides from PDF")
        return annotation_slides
    
    def _extract_figure_captions(self, page_text: str) -> List[str]:
        """Extract figure captions from page text"""
        captions = []
        
        # Look for patterns like "Figure 3.12" or "Fig. 3.13" followed by description
        import re
        
        # Pattern to match figure captions
        figure_patterns = [
            r'Figure\s+\d+\.\d+[^.]*\.([^.]*)',  # Figure 3.12. Description
            r'Fig\.\s+\d+\.\d+[^.]*\.([^.]*)',   # Fig. 3.13. Description
            r'FIGURE\s+\d+\.\d+[^.]*\.([^.]*)',  # FIGURE 3.12. Description
        ]
        
        for pattern in figure_patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            for match in matches:
                caption = match.strip()
                if caption and len(caption) > 10:  # Only meaningful captions
                    captions.append(caption)
        
        # If no figure captions found, look for image descriptions
        if not captions:
            # Look for text that might describe images
            lines = page_text.split('\n')
            for line in lines:
                line = line.strip()
                if line and ('showing' in line.lower() or 'depicting' in line.lower() or 'illustrating' in line.lower()):
                    captions.append(line)
        
        print(f"Extracted {len(captions)} figure captions: {captions}")
        return captions
    
    def _extract_figure_annotations(self, page_text: str) -> List[str]:
        """Extract figure annotations from page text for text-only mode
        
        Only extracts figures that start at the beginning of sentences/paragraphs,
        not figures referenced within normal text.
        """
        annotations = []
        import re
        
        # Split text into sentences/paragraphs to check if figure is at the start
        # First, split by double newlines (paragraphs)
        paragraphs = page_text.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # Check if paragraph starts with a figure reference
            figure_patterns = [
                r'^(Figure\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',  # Figure 2.16. Description
                r'^(Fig\.\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',   # Fig. 3.13. Description
                r'^(FIGURE\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',  # FIGURE 3.12. Description
            ]
            
            for pattern in figure_patterns:
                match = re.match(pattern, paragraph, re.IGNORECASE | re.DOTALL)
                if match:
                    figure_ref = match.group(1).strip()
                    description = match.group(2).strip()
                    
                    if description and len(description) > 20:  # Only meaningful descriptions
                        full_annotation = f"{figure_ref} {description}"
                        annotations.append(full_annotation)
                        break  # Found a figure, move to next paragraph
        
        # Also check individual lines that might be figure captions
        lines = page_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line starts with figure reference (standalone caption)
            figure_patterns = [
                r'^(Figure\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',  # Figure 2.16. Description
                r'^(Fig\.\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',   # Fig. 3.13. Description
                r'^(FIGURE\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',  # FIGURE 3.12. Description
            ]
            
            for pattern in figure_patterns:
                match = re.match(pattern, line, re.IGNORECASE | re.DOTALL)
                if match:
                    figure_ref = match.group(1).strip()
                    description = match.group(2).strip()
                    
                    if description and len(description) > 20:  # Only meaningful descriptions
                        full_annotation = f"{figure_ref} {description}"
                        # Avoid duplicates (already found in paragraphs)
                        if full_annotation not in annotations:
                            annotations.append(full_annotation)
                    break
        
        print(f"Extracted {len(annotations)} figure annotations")
        return annotations
    
    def _extract_table_annotations(self, page_text: str) -> List[str]:
        """Extract table annotations from page text for text-only mode
        
        Looks for table captions and content that appears to be in table frames.
        """
        annotations = []
        import re
        
        # Split text into paragraphs to better identify table content
        paragraphs = page_text.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # Check if paragraph starts with a table reference
            table_patterns = [
                r'^(Table\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',  # Table 3.1. Description
                r'^(Table\s+\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',       # Table 2. Description
                r'^(TABLE\s+\d+\.\d+[^.]*\.)([^.]*(?:\.[^.]*)*)',  # TABLE 3.1. Description
            ]
            
            for pattern in table_patterns:
                match = re.match(pattern, paragraph, re.IGNORECASE | re.DOTALL)
                if match:
                    table_ref = match.group(1).strip()
                    description = match.group(2).strip()
                    
                    if description and len(description) > 20:  # Only meaningful descriptions
                        full_annotation = f"{table_ref} {description}"
                        annotations.append(full_annotation)
                        break  # Found a table, move to next paragraph
        
        # Also look for table-like content (structured data patterns)
        # Look for lines that might be table headers or content
        lines = page_text.split('\n')
        table_content_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for table-like patterns:
            # 1. Lines with multiple tab-separated or space-separated columns
            # 2. Lines that look like table headers (short phrases separated by spaces/tabs)
            # 3. Lines with consistent spacing that might be table rows
            
            # Pattern for tab-separated values
            if '\t' in line and len(line.split('\t')) >= 2:
                table_content_lines.append(line)
            # Pattern for space-separated columns (but not too many spaces)
            elif re.search(r'\s{2,}', line) and len(line.split()) >= 2 and len(line.split()) <= 10:
                table_content_lines.append(line)
            # Pattern for table headers (short capitalized words)
            elif re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*$', line) and len(line.split()) <= 6:
                table_content_lines.append(line)
        
        # If we found table-like content, group it
        if table_content_lines:
            # Group consecutive table lines
            table_groups = []
            current_group = []
            
            for line in table_content_lines:
                if current_group and line in lines:
                    # Check if this line is consecutive with the previous group
                    current_line_index = lines.index(line)
                    last_line_index = lines.index(current_group[-1])
                    
                    if current_line_index - last_line_index <= 2:  # Within 2 lines
                        current_group.append(line)
                    else:
                        # Start a new group
                        if current_group:
                            table_groups.append(current_group)
                        current_group = [line]
                else:
                    current_group.append(line)
            
            if current_group:
                table_groups.append(current_group)
            
            # Convert table groups to annotations
            for i, group in enumerate(table_groups):
                if len(group) >= 2:  # Only include groups with multiple lines
                    table_content = " | ".join(group[:5])  # Limit to first 5 lines
                    if len(table_content) > 50:  # Only meaningful table content
                        annotations.append(f"Table Content: {table_content}")
        
        print(f"Extracted {len(annotations)} table annotations")
        return annotations
    
    def _combine_text_and_image_slides(self, text_slides: List[Dict[str, Any]], image_slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Combine text and image slides in appropriate order"""
        combined_slides = []
        
        # Start with text slides
        for i, text_slide in enumerate(text_slides):
            combined_slides.append(text_slide)
            
            # After every 2-3 text slides, insert an image slide if available
            if (i + 1) % 3 == 0 and image_slides:
                image_slide = image_slides.pop(0)  # Take the next image slide
                combined_slides.append(image_slide)
        
        # Add any remaining image slides at the end
        combined_slides.extend(image_slides)
        
        print(f"Combined {len(combined_slides)} total slides")
        return combined_slides
    
    def _translate_detailed_slides(self, slides_data: list, target_language: str) -> list:
        """Translate detailed slide content to target language with robust error handling"""
        if not self.translation_service.is_configured():
            raise Exception("Translation service not configured")
        
        print(f"🔄 Starting translation of {len(slides_data)} slides to {target_language}")
        
        # Collect all texts that need translation for batch processing
        texts_to_translate = []
        text_mapping = []  # Track where each text came from
        
        for slide_idx, slide in enumerate(slides_data):
            # Collect title
            if 'title' in slide and slide['title'] and str(slide['title']).strip():
                texts_to_translate.append(str(slide['title']))
                text_mapping.append(('title', slide_idx))
            
            # Collect content
            if 'content' in slide:
                if isinstance(slide['content'], list):
                    for content_idx, item in enumerate(slide['content']):
                        if item and str(item).strip():
                            texts_to_translate.append(str(item))
                            text_mapping.append(('content', slide_idx, content_idx))
                else:
                    if slide['content'] and str(slide['content']).strip():
                        texts_to_translate.append(str(slide['content']))
                        text_mapping.append(('content', slide_idx, 'string'))
            
            # Collect image descriptions
            if 'image_description' in slide and slide['image_description'] and str(slide['image_description']).strip():
                texts_to_translate.append(str(slide['image_description']))
                text_mapping.append(('image_description', slide_idx))
            
            # Collect annotation descriptions (for text-only mode)
            if 'annotation_descriptions' in slide:
                for ann_idx, desc in enumerate(slide['annotation_descriptions']):
                    if desc and str(desc).strip():
                        texts_to_translate.append(str(desc))
                        text_mapping.append(('annotation_descriptions', slide_idx, ann_idx))
        
        # Translate all texts in batch
        if texts_to_translate:
            print(f"🔄 Translating {len(texts_to_translate)} text items in batch...")
            try:
                translated_texts = self.translation_service.translate_batch(texts_to_translate, target_language)
                print(f"✅ Successfully translated {len(translated_texts)} text items")
            except Exception as e:
                print(f"❌ Batch translation failed: {e}")
                print("🔄 Falling back to individual translation...")
                
                # Fallback to individual translation
                translated_texts = []
                for i, text in enumerate(texts_to_translate):
                    try:
                        translated_text = self.translation_service.translate_text(text, target_language)
                        translated_texts.append(translated_text)
                        print(f"✅ Translated item {i+1}/{len(texts_to_translate)}")
                    except Exception as individual_error:
                        print(f"⚠️ Failed to translate item {i+1}: {individual_error}")
                        translated_texts.append(text)  # Keep original text
        else:
            translated_texts = []
        
        # Map translated texts back to slides
        translated_slides = []
        for slide in slides_data:
            translated_slide = slide.copy()
            translated_slides.append(translated_slide)
        
        # Apply translations
        for translated_text, mapping in zip(translated_texts, text_mapping):
            slide_idx = mapping[1]
            
            if mapping[0] == 'title':
                translated_slides[slide_idx]['title'] = translated_text
            elif mapping[0] == 'content':
                if len(mapping) == 3:  # List content
                    content_idx = mapping[2]
                    if content_idx != 'string':
                        translated_slides[slide_idx]['content'][content_idx] = translated_text
                    else:
                        translated_slides[slide_idx]['content'] = translated_text
            elif mapping[0] == 'image_description':
                translated_slides[slide_idx]['image_description'] = translated_text
            elif mapping[0] == 'annotation_descriptions':
                ann_idx = mapping[2]
                translated_slides[slide_idx]['annotation_descriptions'][ann_idx] = translated_text
        
        print(f"✅ Translation completed for {len(translated_slides)} slides")
        return translated_slides
    
    def _translate_image_descriptions(self, slides_data: list, target_language: str) -> list:
        """Translate image descriptions in slides data to target language"""
        if not self.translation_service.is_configured():
            raise Exception("Translation service not configured")
        
        translated_slides = []
        
        for slide in slides_data:
            translated_slide = slide.copy()
            
            # Translate image descriptions
            if 'image_descriptions' in slide:
                translated_image_descriptions = []
                for desc in slide['image_descriptions']:
                    if desc and str(desc).strip():
                        translated_image_descriptions.append(
                            self.translation_service.translate_text(str(desc), target_language)
                        )
                translated_slide['image_descriptions'] = translated_image_descriptions
            
            translated_slides.append(translated_slide)
        
        return translated_slides
    
    def _create_detailed_presentation(self, slides_data: list, output_path: str, pdf_title: str, pdf_content: Dict[str, Any]) -> str:
        """Create the final detailed presentation file"""
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Create detailed presentation
        return self.presentation_builder.create_medical_presentation(
            slides_data=slides_data,
            output_path=output_path,
            pdf_title=pdf_title,
            pdf_content=pdf_content
        )
    
    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                print(f"Warning: Could not clean up temp directory: {e}")
    
    def get_processing_status(self) -> Dict[str, Any]:
        """Get current processing status"""
        return {
            'pdf_loaded': self.pdf_processor is not None,
            'translation_available': self.translation_service.is_configured(),
            'temp_dir': self.temp_dir
        }
    
    def validate_inputs(self, pdf_filename: str, target_language: Optional[str] = None) -> Dict[str, Any]:
        """Validate input parameters"""
        errors = []
        warnings = []
        
        # Check PDF filename (not file existence - that's handled during processing)
        if not pdf_filename:
            errors.append("PDF filename is required")
        elif not pdf_filename.lower().endswith('.pdf'):
            errors.append("File must be a PDF")
        
        # Check target language
        if target_language:
            if target_language not in SUPPORTED_LANGUAGES.values():
                errors.append(f"Unsupported language: {target_language}")
            
            if not self.translation_service.is_configured():
                warnings.append("Translation service not configured - translation will be skipped")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
