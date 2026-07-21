
import pymupdf  # This is correct — fitz is an alias

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract all plain text from a PDF, separating pages with form feed.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        str: Combined plain text from all pages.
    """
    with pymupdf.open(pdf_path) as doc:
        return "\f".join(page.get_text("text") for page in doc)


# print(extract_text_from_pdf("./samples/pdfs/am_journal_case_reports_2024.pdf"))