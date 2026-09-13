import docx
from app.services.parsers.base import BaseParser


class DOCXParser(BaseParser):
    def parse(self, file_path: str) -> str:
        try:
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            raise ValueError(f"Failed to parse DOCX file: {str(e)}")
