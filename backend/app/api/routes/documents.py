"""The encrypted library. Every body here is ciphertext made in the owner's
browser; the server checks sizes, quotas and ownership, and nothing else."""

from fastapi import APIRouter, Depends, HTTPException, Path, status

from ...db import documents
from ...db.users import User
from ...settings import Settings
from ..deps import require_user, settings
from ..schemas import DocumentIn, DocumentPatch

router = APIRouter(prefix="/documents", tags=["documents"])

DocId = Path(pattern=r"^[A-Za-z0-9_-]{16}$")
NOT_FOUND = "That document is not in your library."


def _check_size(body: DocumentIn, s: Settings) -> None:
    # base64 adds a third; the limit applies to the encrypted bytes
    if (len(body.meta) + len(body.body)) * 3 // 4 > s.max_document_bytes:
        raise HTTPException(413, "This document is too large to save.")


@router.get("")
def list_documents(user: User = Depends(require_user)) -> dict:
    return {"documents": documents.list_for(user.id), "stats": documents.stats(user.id)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_document(body: DocumentIn, user: User = Depends(require_user), s: Settings = Depends(settings)) -> dict:
    _check_size(body, s)
    if documents.count(user.id) >= s.max_documents_per_user:
        raise HTTPException(409, f"Your library is full ({s.max_documents_per_user} documents). Delete some to add more.")
    return documents.create(user.id, body.meta, body.body)


@router.get("/{doc_id}")
def get_document(doc_id: str = DocId, user: User = Depends(require_user)) -> dict:
    found = documents.get(user.id, doc_id)
    if not found:
        raise HTTPException(404, NOT_FOUND)
    return found


@router.put("/{doc_id}")
def replace_document(body: DocumentIn, doc_id: str = DocId, user: User = Depends(require_user),
                     s: Settings = Depends(settings)) -> dict:
    _check_size(body, s)
    if not documents.update(user.id, doc_id, body.meta, body.body):
        raise HTTPException(404, NOT_FOUND)
    return {"ok": True}


@router.patch("/{doc_id}")
def patch_document(body: DocumentPatch, doc_id: str = DocId, user: User = Depends(require_user)) -> dict:
    if not documents.set_starred(user.id, doc_id, body.starred):
        raise HTTPException(404, NOT_FOUND)
    return {"ok": True}


@router.delete("/{doc_id}")
def delete_document(doc_id: str = DocId, user: User = Depends(require_user)) -> dict:
    if not documents.delete(user.id, doc_id):
        raise HTTPException(404, NOT_FOUND)
    return {"ok": True}
