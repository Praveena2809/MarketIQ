from app.services.parsers.base import BaseParser


class TXTParser(BaseParser):
    def parse(self, file_path: str) -> str:
        encodings = ["utf-8", "latin-1", "cp1252"]
        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except Exception as e:
                raise ValueError(f"Failed to read TXT file: {str(e)}")
        raise ValueError("Failed to decode text file with standard encodings.")
