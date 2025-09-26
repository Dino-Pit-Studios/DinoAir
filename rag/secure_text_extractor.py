"""
Secure Text Extractor Factory for RAG File Search System

This module provides secure text extraction capabilities with built-in protection
against known vulnerabilities, including the PyPDF2 infinite loop issue.

It serves as the integration point between the RAG system and safe text extraction
utilities for various file formats.
"""

import logging
import time
from pathlib import Path
from typing import Any

from utils import SafePDFProcessor

logger = logging.getLogger(__name__)


class SecureTextExtractor:
    """
    Factory for secure text extraction from various file formats.

    This class coordinates text extraction across multiple file types while
    ensuring security protections are in place for known vulnerabilities.
    """

    SUPPORTED_EXTENSIONS = {
        ".pdf": "pdf",
        ".txt": "text",
        ".md": "markdown",
        ".py": "python",
        ".js": "javascript",
        ".html": "html",
        ".json": "json",
        ".csv": "csv",
    }

    def __init__(
        self,
        pdf_timeout: int = 30,
        pdf_max_pages: int = 1000,
        pdf_max_file_size: int = 50 * 1024 * 1024,  # 50MB
        enable_pdf_extraction: bool = True,
    ):
        """
        Initialize SecureTextExtractor with security limits.

        Args:
            pdf_timeout: Maximum time for PDF processing (seconds)
            pdf_max_pages: Maximum pages to process from PDF
            pdf_max_file_size: Maximum PDF file size (bytes)
            enable_pdf_extraction: Whether to enable PDF extraction
        """
        self.pdf_timeout = pdf_timeout
        self.pdf_max_pages = pdf_max_pages
        self.pdf_max_file_size = pdf_max_file_size
        self.enable_pdf_extraction = enable_pdf_extraction

        # Initialize PDF processor if enabled
        if enable_pdf_extraction:
            try:
                self.pdf_processor = SafePDFProcessor(
                    timeout=pdf_timeout,
                    max_pages=pdf_max_pages,
                    max_file_size=pdf_max_file_size,
                )
                logger.info("Secure PDF extraction enabled with safety protections")
            except ImportError:
                logger.warning("PyPDF2 not available - PDF extraction disabled")
                self.pdf_processor = None
                self.enable_pdf_extraction = False
        else:
            self.pdf_processor = None

        logger.info(
            "SecureTextExtractor initialized (PDF: %s)",
            "enabled" if self.enable_pdf_extraction else "disabled",
        )

    def get_supported_extensions(self) -> list[str]:
        """
        Get list of supported file extensions.

        Returns:
            List of supported file extensions including dot prefix
        """
        extensions = list(self.SUPPORTED_EXTENSIONS.keys())
        if not self.enable_pdf_extraction:
            extensions = [ext for ext in extensions if ext != ".pdf"]
        return extensions

    def can_extract(self, file_path: str | Path) -> bool:
        """
        Check if text can be extracted from the given file.

        Args:
            file_path: Path to the file

        Returns:
            True if extraction is supported
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        if extension == ".pdf":
            return self.enable_pdf_extraction

        return extension in self.SUPPORTED_EXTENSIONS

    def extract_text(self, file_path: str | Path, max_size: int | None = None) -> dict[str, Any]:
        """
        Extract text from file with appropriate security measures.

        Args:
            file_path: Path to file
            max_size: Optional maximum file size limit

        Returns:
            Dictionary containing extraction results with keys:
                - success: bool
                - text: str (extracted text)
                - file_type: str
                - processing_time: float
                - warnings: List[str]
                - error: str (if failed)
        """
        start_time = time.time()
        path = Path(file_path)
        extension = path.suffix.lower()

        result = {
            "success": False,
            "text": "",
            "file_type": self.SUPPORTED_EXTENSIONS.get(extension, "unknown"),
            "processing_time": 0,
            "warnings": [],
            "error": None,
        }

        try:
            if not path.exists():
                result["error"] = f"File does not exist: {file_path}"
                return result

            if not path.is_file():
                result["error"] = f"Path is not a file: {file_path}"
                return result

            # Check file size if specified
            file_size = path.stat().st_size
            if max_size and file_size > max_size:
                result["error"] = f"File too large: {file_size} bytes (max: {max_size})"
                return result

            # Route to appropriate extractor based on file type
            if extension == ".pdf":
                if not self.enable_pdf_extraction:
                    result["error"] = "PDF extraction is disabled"
                    return result

                pdf_result = self.pdf_processor.extract_text(file_path)

                # Map PDF result to our standard format
                result["success"] = pdf_result["success"]
                result["text"] = pdf_result["text"]
                result["warnings"] = pdf_result["warnings"]
                result["error"] = pdf_result["error"]

                # Add PDF-specific metadata
                result["pages_processed"] = pdf_result.get("pages_processed", 0)
                result["total_pages"] = pdf_result.get("total_pages", 0)

            elif extension in [".txt", ".md", ".py", ".js", ".html", ".json", ".csv"]:
                # Handle plain text files
                text_result = self._extract_plain_text(path, max_size)
                result.update(text_result)
            else:
                result["error"] = f"Unsupported file type: {extension}"

        except Exception as e:
            result["error"] = f"Unexpected error during extraction: {str(e)}"
            logger.error("Error extracting text from %s: %s", file_path, str(e))

        finally:
            result["processing_time"] = time.time() - start_time

        return result

    def _extract_plain_text(self, file_path: Path, max_size: int | None = None) -> dict[str, Any]:
        """
        Extract text from plain text files with size limits.

        Args:
            file_path: Path to text file
            max_size: Maximum file size to process

        Returns:
            Extraction result dictionary
        """
        result = {"success": False, "text": "", "warnings": []}

        try:
            file_size = file_path.stat().st_size

            # Default size limit of 10MB for text files
            size_limit = max_size or (10 * 1024 * 1024)

            if file_size > size_limit:
                result["warnings"].append(
                    f"File size ({file_size} bytes) exceeds limit ({size_limit} bytes)"
                )
                # Read only up to the limit
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    result["text"] = f.read(size_limit)
                result["warnings"].append("File content truncated due to size limit")
            else:
                # Read entire file
                if "../" in str(file_path) or "..\\" in str(file_path):
                    raise Exception("Invalid file path")
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    result["text"] = f.read()

            result["success"] = True

        except UnicodeDecodeError:
            # Try different encodings
            for encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                try:
                    if "../" in str(file_path) or "..\\" in str(file_path):
                        raise Exception("Invalid file path")
                    with open(file_path, encoding=encoding, errors="replace") as f:
                        result["text"] = f.read()
                    result["success"] = True
                    result["warnings"].append(f"Decoded using {encoding} encoding")
                    break
                except (OSError, ValueError):
                    continue

            if not result["success"]:
                result["error"] = "Could not decode file with any supported encoding"

        except Exception as e:
            result["error"] = f"Error reading text file: {str(e)}"

        return result

    def is_file_safe(self, file_path: str | Path) -> dict[str, Any]:
        """
        Check if a file appears safe for text extraction.

        Args:
            file_path: Path to file to check

        Returns:
            Safety assessment dictionary
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        result = {
            "safe": False,
            "file_type": self.SUPPORTED_EXTENSIONS.get(extension, "unknown"),
            "checks_passed": [],
            "checks_failed": [],
            "warnings": [],
        }

        try:
            # Basic file checks
            if not path.exists():
                result["checks_failed"].append("File does not exist")
                return result

            if not path.is_file():
                result["checks_failed"].append("Path is not a file")
                return result

            result["checks_passed"].append("File exists and is accessible")

            # File size check
            file_size = path.stat().st_size
            if file_size > 100 * 1024 * 1024:  # 100MB
                result["warnings"].append(f"Large file: {file_size} bytes")
            else:
                result["checks_passed"].append("File size reasonable")

            # Type-specific safety checks
            if extension == ".pdf" and self.enable_pdf_extraction:
                # Use PDF processor's safety check
                pdf_safety = self.pdf_processor.is_pdf_safe(file_path)
                result["safe"] = pdf_safety["safe"]
                result["checks_passed"].extend(pdf_safety["checks_passed"])
                result["checks_failed"].extend(pdf_safety["checks_failed"])
                result["warnings"].extend(pdf_safety["warnings"])

            elif extension in [".txt", ".md", ".py", ".js", ".html", ".json", ".csv"]:
                # Text files are generally safe
                result["checks_passed"].append("Plain text format")
                result["safe"] = True

            elif extension in [".docx", ".doc"]:
                result["warnings"].append("Word document processing not implemented")
                result["safe"] = False

            else:
                result["checks_failed"].append("Unsupported file type")

        except Exception as e:
            result["checks_failed"].append(f"Safety check failed: {str(e)}")

        return result

    def get_extraction_stats(self) -> dict[str, Any]:
        """
        Get statistics about extraction capabilities and limits.

        Returns:
            Statistics dictionary
        """
        stats = {
            "supported_extensions": self.get_supported_extensions(),
            "pdf_extraction_enabled": self.enable_pdf_extraction,
        }

        if self.enable_pdf_extraction:
            stats.update(
                {
                    "pdf_timeout": self.pdf_timeout,
                    "pdf_max_pages": self.pdf_max_pages,
                    "pdf_max_file_size": self.pdf_max_file_size,
                }
            )

        return stats


# Convenience functions
def create_secure_text_extractor(
    pdf_timeout: int = 30, pdf_max_pages: int = 1000, enable_pdf: bool = True
) -> SecureTextExtractor:
    """
    Create SecureTextExtractor with specified settings.

    Args:
        pdf_timeout: PDF processing timeout
        pdf_max_pages: Maximum PDF pages to process
        enable_pdf: Whether to enable PDF extraction

    Returns:
        SecureTextExtractor instance
    """
    return SecureTextExtractor(
        pdf_timeout=pdf_timeout,
        pdf_max_pages=pdf_max_pages,
        enable_pdf_extraction=enable_pdf,
    )


def extract_text_secure(
    file_path: str | Path, pdf_timeout: int = 30, max_size: int | None = None
) -> str:
    """
    Extract text from file using secure methods.

    Args:
        file_path: Path to file
        pdf_timeout: PDF processing timeout
        max_size: Maximum file size

    Returns:
        Extracted text (empty string if extraction fails)
    """
    extractor = SecureTextExtractor(pdf_timeout=pdf_timeout)
    result = extractor.extract_text(file_path, max_size=max_size)

    if result["success"]:
        return result["text"]
    logger.error("Failed to extract text from %s: %s", file_path, result["error"])
    return ""
