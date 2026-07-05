import io
import logging
from typing import List
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from sqlalchemy.orm import Session

from core.rag_manager import RAGManager
from models.database import get_db
from models.metadata import Company, DocumentLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["companies"])
rag_manager = RAGManager()

def extract_text_from_file(filename: str, body: bytes) -> str:
    """Helper to extract text from raw bytes based on extension (PDF/DOCX/PPTX/Text)"""
    fn = filename.lower()
    if fn.endswith('.pdf'):
        try:
            import PyPDF2
            pdf_file = io.BytesIO(body)
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
            return text
        except Exception as e:
            logger.error(f"Failed to parse PDF {filename}: {e}")
            raise ValueError(f"Could not parse PDF document: {str(e)}")
    elif fn.endswith('.docx'):
        try:
            import docx
            doc = docx.Document(io.BytesIO(body))
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text += cell.text + " "
                    text += "\n"
            return text
        except Exception as e:
            logger.error(f"Failed to parse DOCX {filename}: {e}")
            raise ValueError(f"Could not parse DOCX document: {str(e)}")
    elif fn.endswith('.pptx') or fn.endswith('.ppt'):
        try:
            from pptx import Presentation
            prs = Presentation(io.BytesIO(body))
            text = ""
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        text += shape.text + "\n"
            return text
        except Exception as e:
            logger.error(f"Failed to parse PPTX {filename}: {e}")
            raise ValueError(f"Could not parse PPTX presentation: {str(e)}")
    else:
        try:
            return body.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Failed to decode text file {filename}: {e}")
            raise ValueError(f"Could not decode file as text: {str(e)}")

@router.post("/", summary="Create a new company")
async def create_company(name: str, phone_number: str, db: Session = Depends(get_db)):
    # Clean phone number
    cleaned_phone = phone_number.replace("+", "").strip()
    
    # Check if phone number already exists
    existing = db.query(Company).filter(Company.phone_number == cleaned_phone).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Phone number {phone_number} is already registered to company {existing.name}")
        
    company_id = str(uuid.uuid4())
    company = Company(
        company_id=company_id,
        name=name,
        phone_number=cleaned_phone,
        metadata_json={}
    )
    
    try:
        db.add(company)
        db.commit()
        # Initialize tenant Chroma collection
        rag_manager.init_index(company_id)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create company: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
    return {"company_id": company_id, "name": name, "phone_number": cleaned_phone}

@router.get("/", summary="List all companies")
async def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [{"company_id": c.company_id, "name": c.name, "phone_number": c.phone_number} for c in companies]

@router.get("/{company_id}", summary="Get company details")
async def get_company(company_id: str, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Fetch document logs
    docs = db.query(DocumentLog).filter(DocumentLog.company_id == company_id).all()
    documents = [{"id": d.id, "filename": d.filename, "size_bytes": d.size_bytes, "uploaded_at": d.uploaded_at, "status": d.status} for d in docs]
    
    return {
        "company_id": company.company_id,
        "name": company.name,
        "phone_number": company.phone_number,
        "documents": documents
    }

@router.delete("/{company_id}", summary="Delete a company and its RAG data")
async def delete_company(company_id: str, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    try:
        # Delete document logs
        db.query(DocumentLog).filter(DocumentLog.company_id == company_id).delete()
        # Delete company registry
        db.delete(company)
        db.commit()
        
        # Delete index from Chroma
        rag_manager.delete_index(company_id)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete company {company_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
    return {"deleted": True, "company_id": company_id}

@router.post("/{company_id}/documents", summary="Upload documents for a company")
async def upload_documents(company_id: str, files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    uploaded_files = []
    
    for upload in files:
        body = await upload.read()
        try:
            text = extract_text_from_file(upload.filename, body)
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))
            
        # Write log entry
        doc_log = DocumentLog(
            company_id=company_id,
            filename=upload.filename,
            size_bytes=len(body),
            status="processing"
        )
        db.add(doc_log)
        db.commit()
        db.refresh(doc_log)
        
        try:
            # Process in RAG manager (upload to S3, embed via Gemini, store in Chroma)
            await rag_manager.upload_documents(company_id, upload.filename, body, text)
            doc_log.status = "processed"
            db.commit()
            uploaded_files.append({"id": doc_log.id, "filename": upload.filename, "status": "processed"})
        except Exception as e:
            logger.error(f"Failed to index document {upload.filename}: {e}")
            doc_log.status = "failed"
            db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to index {upload.filename}: {str(e)}")
            
    return {"status": "success", "company_id": company_id, "files": uploaded_files}

@router.get("/{company_id}/search", summary="Search the RAG store for a company")
async def search_company(company_id: str, q: str, top_k: int = 3, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    results = await rag_manager.search(company_id, q, top_k)
    return [{"chunk": r["chunk_text"], "source": r["metadata"].get("source")} for r in results]

@router.delete("/{company_id}/documents/{document_id}", summary="Delete a document and its RAG vectors")
async def delete_document(company_id: str, document_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    doc = db.query(DocumentLog).filter(DocumentLog.id == document_id, DocumentLog.company_id == company_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document log not found")
        
    try:
        # Delete from S3 and Chroma
        rag_manager.delete_document(company_id, doc.filename)
        
        # Delete database log
        db.delete(doc)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
    return {"deleted": True, "document_id": document_id, "filename": doc.filename}

from pydantic import BaseModel

class RawTextInput(BaseModel):
    text: str
    source_name: str

@router.post("/{company_id}/webpages", summary="Crawl and index a web page")
async def index_webpage(company_id: str, url: str, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    try:
        import aiohttp
        from bs4 import BeautifulSoup
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=400, detail=f"Webpage returned status {resp.status}")
                html = await resp.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
            
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = "\n".join(chunk for chunk in chunks if chunk)
        
        if not clean_text.strip():
            raise ValueError("Cleaned webpage content is empty.")
            
    except Exception as e:
        logger.error(f"Failed to fetch or parse webpage {url}: {e}")
        raise HTTPException(status_code=400, detail=f"Webpage fetch failed: {str(e)}")
        
    filename = url.replace("https://", "").replace("http://", "").replace("/", "_").replace("?", "_").replace("&", "_")
    if len(filename) > 100:
        filename = filename[:97] + "..."
    filename = f"webpage_{filename}.txt"
    
    doc_log = DocumentLog(
        company_id=company_id,
        filename=filename,
        size_bytes=len(clean_text.encode('utf-8')),
        status="processing"
    )
    db.add(doc_log)
    db.commit()
    db.refresh(doc_log)
    
    try:
        await rag_manager.upload_documents(company_id, filename, clean_text.encode('utf-8'), clean_text)
        doc_log.status = "processed"
        db.commit()
    except Exception as e:
        logger.error(f"Failed to index webpage {url}: {e}")
        doc_log.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to index webpage: {str(e)}")
        
    return {"status": "success", "company_id": company_id, "filename": filename, "source": url}

@router.post("/{company_id}/text", summary="Index raw text messages or custom instructions")
async def index_raw_text(company_id: str, payload: RawTextInput, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    text_content = payload.text.strip()
    if not text_content:
        raise HTTPException(status_code=400, detail="Text content cannot be empty")
        
    source_name = payload.source_name.strip()
    if not source_name.endswith('.txt'):
        source_name = f"{source_name}.txt"
        
    import time
    timestamp = int(time.time())
    filename = f"text_{timestamp}_{source_name}"
    
    doc_log = DocumentLog(
        company_id=company_id,
        filename=filename,
        size_bytes=len(text_content.encode('utf-8')),
        status="processing"
    )
    db.add(doc_log)
    db.commit()
    db.refresh(doc_log)
    
    try:
        await rag_manager.upload_documents(company_id, filename, text_content.encode('utf-8'), text_content)
        doc_log.status = "processed"
        db.commit()
    except Exception as e:
        logger.error(f"Failed to index raw text {filename}: {e}")
        doc_log.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to index raw text: {str(e)}")
        
    return {"status": "success", "company_id": company_id, "filename": filename}
