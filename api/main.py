import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
try:
    from .orb_substrate import OrbSubstrateService
except ImportError:
    from orb_substrate import OrbSubstrateService

# Ensure the electron src directory is in the path to import components
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root / "electron" / "src"))
sys.path.append(str(project_root.parent))

from components.core_4_minds.tribunal import FourMindTribunal
from substrate.learning_modules.abby_protocol.core.router import router as abby_router
from substrate.spruk_legacy_orb.core.presence_router import router as legacy_router

app = FastAPI(title="Spruked ORB Backend", version="1.0.0")

# Setup CORS to allow requests from the web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to "https://spruked.com" in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(abby_router, prefix="/abby", tags=["abby-protocol"])
app.include_router(legacy_router, prefix="/legacy", tags=["spruk-legacy-orb"])

# Initialize the Council once on startup
# Using the path to the original electron folder to ensure it finds the skg files
skg_path = project_root / "electron" / "src" / "components" / "core_4_minds"
council = FourMindTribunal(skg_path=str(skg_path))
orb_substrate = OrbSubstrateService()

class Query(BaseModel):
    prompt: str
    context: Dict[str, Any] | None = None


class OrbContactSearchQuery(BaseModel):
    query: str
    limit: int = 20


class OrbMailSearchQuery(BaseModel):
    query: str
    folder: str | None = None
    limit: int = 25


class OrbMailDraftCreateQuery(BaseModel):
    to: str
    subject: str
    text: str
    account: str | None = None


class OrbMailMessageUpdateQuery(BaseModel):
    read: bool | None = None
    starred: bool | None = None
    archived: bool | None = None
    folder: str | None = None


class OrbCrmNoteAddQuery(BaseModel):
    contact_id: str
    note: str


class OrbCrmActivityAddQuery(BaseModel):
    contact_id: str
    activity_type: str
    summary: str
    metadata: Dict[str, Any] | None = None


def _require_tool(tool_name: str) -> None:
    decision = orb_substrate.authorize_tool(tool_name, explicit_user_approval=False)
    if not decision.get("allowed"):
        raise HTTPException(status_code=403, detail=decision)

@app.post("/api/v1/tribunal")
async def ask_the_council(query: Query):
    """
    Asynchronous endpoint to handle the 'Council of Four' logic.
    For the web demo, this prevents timeouts and processes the stimulus.
    """
    try:
        # Construct stimulus from the user's prompt
        stimulus = {"prompt": query.prompt, "context": query.context or {}}
        
        # This calls Cali's core adjudication logic to generate exact epistemic shadows
        shadows = council.generate_epistemic_shadow(stimulus)
        
        # Determine the leading mind for visual feedback in the UI
        leading_mind = max(shadows.items(), key=lambda x: x[1]['confidence'])[0]
        confidence = shadows[leading_mind]['confidence']
        
        # Synthesize a temporary generic text response based on the leading mind
        response_text = f"The tribunal has evaluated your input. {leading_mind.title()} has taken the lead with a confidence weight of {confidence}."
        
        # Simulated delay to represent the "thinking" process over WebSockets/Streaming later
        await asyncio.sleep(1.0)
        
        return {
            "status": "success",
            "response": response_text,
            "metadata": {
                "leading_mind": leading_mind,
                "confidence": confidence,
                "shadows": shadows,
                "vault_update": "pending"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ORB System Operational", "layer": "FastAPI Core"}


@app.get("/api/v1/readiness")
async def readiness_check():
    return orb_substrate.health_readiness()


@app.post("/api/v1/tools/orb.crm.contacts.search")
async def orb_crm_contacts_search(payload: OrbContactSearchQuery):
    _require_tool("orb.crm.contacts.search")
    return orb_substrate.search_contacts(query=payload.query, limit=payload.limit)


@app.get("/api/v1/tools/orb.crm.pipeline.status")
async def orb_crm_pipeline_status():
    _require_tool("orb.crm.pipeline.status")
    return orb_substrate.pipeline_status()


@app.get("/api/v1/tools/orb.mail.inbox.summary")
async def orb_mail_inbox_summary(limit: int = 25, unread_only: bool = False, account: str | None = None):
    _require_tool("orb.mail.inbox.summary")
    return orb_substrate.inbox_summary(limit=limit, unread_only=unread_only, account=account)


@app.post("/api/v1/tools/orb.mail.search")
async def orb_mail_search(payload: OrbMailSearchQuery):
    _require_tool("orb.mail.search")
    return orb_substrate.search_messages(query=payload.query, folder=payload.folder, limit=payload.limit)


@app.get("/api/v1/tools/orb.mail.message.get/{email_id}")
async def orb_mail_message_get(email_id: str):
    _require_tool("orb.mail.message.get")
    result = orb_substrate.get_message(email_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"email_id not found: {email_id}")
    return result


@app.post("/api/v1/tools/orb.mail.draft.prepare")
async def orb_mail_draft_prepare(payload: OrbMailDraftCreateQuery):
    _require_tool("orb.mail.draft.prepare")
    return orb_substrate.create_draft(
        to=payload.to,
        subject=payload.subject,
        text=payload.text,
        account=payload.account,
    )


@app.patch("/api/v1/tools/orb.mail.message.update/{email_id}")
async def orb_mail_message_update(email_id: str, payload: OrbMailMessageUpdateQuery):
    _require_tool("orb.mail.message.update")
    result = orb_substrate.update_message(
        email_id=email_id,
        read=payload.read,
        starred=payload.starred,
        archived=payload.archived,
        folder=payload.folder,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@app.get("/api/v1/tools/orb.unified.snapshot")
async def orb_unified_snapshot():
    _require_tool("orb.unified.snapshot")
    return orb_substrate.unified_snapshot()


@app.post("/api/v1/tools/orb.crm.note.add")
async def orb_crm_note_add(payload: OrbCrmNoteAddQuery):
    _require_tool("orb.crm.note.add")
    return orb_substrate.add_crm_note(payload.contact_id, payload.note)


@app.post("/api/v1/tools/orb.crm.activity.add")
async def orb_crm_activity_add(payload: OrbCrmActivityAddQuery):
    _require_tool("orb.crm.activity.add")
    return orb_substrate.add_crm_activity(
        contact_id=payload.contact_id,
        activity_type=payload.activity_type,
        summary=payload.summary,
        metadata=payload.metadata,
    )


@app.get("/api/v1/tools")
async def orb_allowed_tools():
    return {"allowed_tools": orb_substrate.list_allowed_tools()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("ORB_API_HOST", "127.0.0.1"), port=int(os.getenv("ORB_API_PORT", "21100")))
