import pandas as pd
from app.services.parsers.base import BaseParser


class CSVParser(BaseParser):
    def parse(self, file_path: str) -> str:
        try:
            df = pd.read_csv(file_path)
            if df.empty:
                return ""
            rows = []
            columns = list(df.columns)
            rows.append(f"CSV Columns: {', '.join(columns)}")
            for idx, row in df.iterrows():
                row_str = ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                rows.append(f"Row {idx + 1}: {row_str}")
            return "\n".join(rows)
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {str(e)}")
