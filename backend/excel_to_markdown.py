#!/usr/bin/env python3
"""
Enhanced Excel to Markdown converter
Based on proven excel-to-markdown library with improved table detection
"""

import pandas as pd
import string
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ExcelToMarkdownConverter:
    """Enhanced Excel to Markdown converter with automatic table detection"""

    def __init__(self):
        self.debug_log = []

    def log_debug(self, message: str):
        """Add debug message to log"""
        self.debug_log.append(message)
        logger.info(message)

    def column_letter_to_index(self, letter: str) -> int:
        """Convert Excel column letter to zero-based index"""
        letter = letter.upper()
        result = 0
        for char in letter:
            if char in string.ascii_uppercase:
                result = result * 26 + (ord(char) - ord("A") + 1)
            else:
                raise ValueError(f"Invalid column letter: {char}")
        return result - 1

    def sanitize_sheet_name(self, sheet_name: str) -> str:
        """Sanitize sheet name for safe filename usage"""
        sanitized = re.sub(r"[^\w\s]", "_", sheet_name).strip().replace(" ", "_")
        return sanitized

    def detect_table_start(self, df: pd.DataFrame) -> Optional[int]:
        """
        Detect the starting row of the table by finding the first row
        that is completely filled within the non-null columns.
        """
        # Identify columns that have any non-null values
        non_null_columns = df.columns[df.notnull().any(axis=0)]
        if len(non_null_columns) == 0:
            return None

        # Get the indices of the leftmost and rightmost non-null columns
        left_col_index = df.columns.get_loc(non_null_columns[0])
        right_col_index = df.columns.get_loc(non_null_columns[-1])

        # Iterate through each row to find the first fully populated row
        for idx, row in df.iterrows():
            row_slice = row.iloc[left_col_index : right_col_index + 1]
            if (
                row_slice.notnull().all()
                and not row_slice.astype(str).str.strip().eq("").any()
            ):
                return idx

        return None

    def get_table_region(self, df: pd.DataFrame) -> Tuple[Optional[int], List]:
        """
        Improved logic to detect all relevant columns based on header names and non-null values.
        """
        start_row = self.detect_table_start(df)
        if start_row is not None:
            self.log_debug(
                f"Automatically detected table starting at row {start_row + 1}"
            )
            # Consider columns with at least 49% non-null values as part of the table
            threshold = 0.49
            valid_cols = [
                col for col in df.columns if df[col].notnull().mean() > threshold
            ]
            return start_row, valid_cols
        else:
            self.log_debug("Automatic table detection failed, using all columns")
            # Fallback: use all columns with some data
            valid_cols = [col for col in df.columns if df[col].notnull().any()]
            return 0, valid_cols

    def dataframe_to_markdown(self, df: pd.DataFrame) -> str:
        """Convert a pandas DataFrame to a Markdown table"""
        if df.empty:
            return ""

        # Clean column names
        df.columns = [
            str(col).strip() if pd.notnull(col) else f"Col_{i}"
            for i, col in enumerate(df.columns)
        ]

        # Generate the header row
        markdown = "| " + " | ".join(str(col) for col in df.columns) + " |\n"
        # Generate the separator row
        markdown += "| " + " | ".join(["---"] * len(df.columns)) + " |\n"

        # Generate each data row
        for _, row in df.iterrows():
            row_values = [str(cell).strip() if pd.notnull(cell) else "" for cell in row]
            markdown += "| " + " | ".join(row_values) + " |\n"

        return markdown

    def excel_to_markdown(self, excel_file: str, sheet_name=0) -> str:
        """
        Convert a specific sheet in an Excel file to a Markdown table.
        """
        try:
            # Read the entire sheet without specifying headers or columns
            df_full = pd.read_excel(
                excel_file, sheet_name=sheet_name, header=None, engine="openpyxl"
            )

            if df_full.empty:
                self.log_debug(f"Sheet {sheet_name} is empty")
                return ""

            # Detect table region
            headers_row, usecols = self.get_table_region(df_full)

            # Read the table with detected parameters
            if headers_row is not None and usecols:
                df = pd.read_excel(
                    excel_file,
                    sheet_name=sheet_name,
                    header=headers_row,
                    usecols=usecols,
                    engine="openpyxl",
                )
            else:
                # Fallback to reading everything
                df = pd.read_excel(excel_file, sheet_name=sheet_name, engine="openpyxl")

            # Drop completely empty rows and columns
            df.dropna(how="all", inplace=True)
            df.dropna(axis=1, how="all", inplace=True)

            # Reset index after dropping rows
            df.reset_index(drop=True, inplace=True)

            # Generate the markdown table
            markdown = self.dataframe_to_markdown(df)

            self.log_debug(
                f"Successfully converted sheet {sheet_name} with {len(df)} rows and {len(df.columns)} columns"
            )

            return markdown

        except Exception as e:
            self.log_debug(f"Error processing sheet {sheet_name}: {str(e)}")
            return f"Error processing sheet {sheet_name}: {str(e)}\n"

    def convert_to_markdown(self, file_path: str) -> Dict[str, Any]:
        """Convert Excel file to markdown with enhanced data extraction"""
        try:
            self.log_debug(f"Opening Excel file: {file_path}")

            # Load the Excel file to get all sheet names
            excel = pd.ExcelFile(file_path, engine="openpyxl")
            sheet_names = excel.sheet_names

            result = {
                "file_name": file_path,
                "sheets": [],
                "total_sheets": len(sheet_names),
                "markdown_content": "",
                "debug_log": [],
            }

            markdown_lines = [f"# Timecard Document: {Path(file_path).name}\n"]

            # Process each sheet
            for sheet_name in sheet_names:
                self.log_debug(f"Processing sheet: '{sheet_name}'")

                # Convert the current sheet to Markdown
                sheet_markdown = self.excel_to_markdown(file_path, sheet_name)

                if sheet_markdown.strip():
                    # Add sheet header and content
                    markdown_lines.append(f"## Sheet: {sheet_name}\n")
                    markdown_lines.append(sheet_markdown)
                    markdown_lines.append("")  # Empty line between sheets

                    # Store sheet info
                    result["sheets"].append(
                        {
                            "sheet_name": sheet_name,
                            "markdown": sheet_markdown,
                            "has_data": True,
                        }
                    )
                else:
                    self.log_debug(f"Sheet '{sheet_name}' has no processable data")
                    result["sheets"].append(
                        {"sheet_name": sheet_name, "markdown": "", "has_data": False}
                    )

            result["markdown_content"] = "\n".join(markdown_lines)
            result["debug_log"] = self.debug_log

            self.log_debug(
                f"Processing complete. Processed {len([s for s in result['sheets'] if s['has_data']])} sheets with data"
            )

            return result

        except Exception as e:
            self.log_debug(f"Error processing Excel file: {str(e)}")
            return {
                "file_name": file_path,
                "error": str(e),
                "debug_log": self.debug_log,
                "sheets": [],
                "total_sheets": 0,
                "markdown_content": f"Error processing file: {str(e)}",
            }


# Usage example and testing
if __name__ == "__main__":
    import os

    converter = ExcelToMarkdownConverter()

    # Find a sample file
    data_dir = "../data"
    if not os.path.exists(data_dir):
        data_dir = "data"

    if os.path.exists(data_dir):
        sample_files = [
            f for f in os.listdir(data_dir) if f.endswith((".xlsx", ".xlsm"))
        ]
        if sample_files:
            test_file = os.path.join(data_dir, sample_files[0])
            print(f"Testing with file: {test_file}")
            result = converter.convert_to_markdown(test_file)

            print(f"Processed {result['total_sheets']} sheets")
            print(
                f"Sheets with data: {len([s for s in result['sheets'] if s['has_data']])}"
            )
            print(f"Markdown preview:\n{result['markdown_content'][:500]}...")

            if result.get("debug_log"):
                print("\nDebug log:")
                for log in result["debug_log"]:
                    print(f"  {log}")
        else:
            print(f"No Excel files found in {data_dir}")
    else:
        print(f"Data directory {data_dir} not found")
