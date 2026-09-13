from pypdf import PdfReader
from app.services.parsers.base import BaseParser


class PDFParser(BaseParser):
    def parse(self, file_path: str) -> str:
        try:
            reader = PdfReader(file_path)
            extracted = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    extracted.append(page_text)
            return "\n\n".join(extracted)
        except Exception as e:
            raise ValueError(f"Failed to parse PDF file: {str(e)}")
