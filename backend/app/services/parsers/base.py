from abc import ABC, abstractmethod
import os


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> str:
        """Extract clean text content from the file."""
        pass


class DocumentParser:
    @staticmethod
    def parse_document(file_path: str, file_type: str) -> str:
        """
        Factory method to route file parsing based on extension/type.
        """
        ext = os.path.splitext(file_path)[1].lower() if file_path else ""
        if not ext and file_type:
            ext = f".{file_type.lower().strip('.')}"

        from app.services.parsers.pdf_parser import PDFParser
        from app.services.parsers.docx_parser import DOCXParser
        from app.services.parsers.csv_parser import CSVParser
        from app.services.parsers.txt_parser import TXTParser

        if ext == ".pdf":
            parser = PDFParser()
        elif ext == ".docx":
            parser = DOCXParser()
        elif ext == ".csv":
            parser = CSVParser()
        elif ext in (".txt", ".md", ".log"):
            parser = TXTParser()
        else:
            raise ValueError(f"Unsupported file format: {ext or file_type}")

        text = parser.parse(file_path)
        if not text or not text.strip():
            raise ValueError(f"Document extraction produced no meaningful text for file: {file_path}")
        return text.strip()
