from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import List
import uuid

from core.rag_manager import RAGManager

router = APIRouter(prefix="/companies", tags=["companies"])

# Initialise a single RAGManager instance (could be injected via Depends in a larger app)
rag_manager = RAGManager()

@router.post("/", summary="Create a new company")
async def create_company(name: str, phone_number: str):
    company_id = str(uuid.uuid4())
    metadata = {"name": name, "phone_number": phone_number}
    try:
        rag_manager.add_company(company_id, metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"company_id": company_id, "metadata": metadata}

@router.get("/{company_id}", summary="Get company details")
async def get_company(company_id: str):
    data = rag_manager.get_company(company_id)
    if not data:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"company_id": company_id, **data}

@router.delete("/{company_id}", summary="Delete a company and its RAG data")
async def delete_company(company_id: str):
    rag_manager.remove_company(company_id)
    return {"deleted": True, "company_id": company_id}

@router.post("/{company_id}/documents", summary="Upload documents for a company", response_model=dict)
async def upload_documents(company_id: str, files: List[UploadFile] = File(...)):
    if not rag_manager.get_company(company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    await rag_manager.upload_documents(company_id, files)
    return {"status": "uploaded", "company_id": company_id}

@router.get("/{company_id}/search", summary="Search the RAG store for a company")
async def search_company(company_id: str, q: str, top_k: int = 5):
    if not rag_manager.get_company(company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    results = await rag_manager.search(company_id, q, top_k)
    # Return only the chunk text and source for simplicity
    return [{"chunk": r["chunk_text"], "source": r["metadata"].get("source")} for r in results]
