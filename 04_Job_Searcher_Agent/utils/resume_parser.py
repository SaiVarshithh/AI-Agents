import io
import docx2txt
import PyPDF2
from typing import Optional

def extract_text_from_file(file_obj, filename: str) -> Optional[str]:
    """
    Extract text from an uploaded in-memory file object (from Streamlit or standard FileIO).
    Supports .pdf and .docx.
    """
    if not file_obj or not filename:
        return None

    filename = filename.lower()
    text = ""
    try:
        if filename.endswith(".pdf"):
            reader = PyPDF2.PdfReader(file_obj)
            pages_text = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    pages_text.append(extracted)
            text = "\n".join(pages_text)
        elif filename.endswith(".docx"):
            text = docx2txt.process(file_obj)
        else:
            return None
    except Exception as e:
        print(f"Failed to parse resume {filename}: {e}")
        return None

    return text.strip() if text else None
