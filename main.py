
import json
from typing import Literal
from pydantic import BaseModel, Field, ValidationError
from fastapi import FastAPI 

app=FastAPI() 




# The allowed shape of the AI answer. Anything else is rejected.
class TriageResult(BaseModel):
    category: Literal["billing", "technical_it", "help_desk", "marketing", "unclear"]
    urgency: Literal["low", "medium", "high"]
    language: Literal["en", "de"]
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0) 

class TriageRequest(BaseModel):
    id: str
    text: str  


def triage(raw_text): 
    # Step 1: turn the text into a dictionary (parsing)
    try:
        data = json.loads(raw_text) # data is dictionary ,  we are calling this json.loads to convert the text into a dictionary , so that our further python code can run it 
    except json.JSONDecodeError: # if json fails this will run and back to the workflow 
        return {
            "needs_review": True,
            "reasons": ["AI answer is not valid JSON"],
            "ai": None,
            "raw_text": raw_text,
        }

    # Step 2: check that the values are allowed (validation)
    try:
        result = TriageResult(**data) # it check if the data is valid
    except (ValidationError, TypeError): # if validation fails this will run and back to the workflow
        return { # this return is for the expect case 
            "needs_review": True,
            "reasons": ["AI answer has missing or wrong values"],
            "ai": None,
            "raw_text": raw_text,
        }

    # Step 3: everything is fine
    return { # this return is when both try passes and now this return is what is sent back to the workflow. 

        "needs_review": False,
        "reasons": [],
        "ai": result.model_dump(), # the model_dump() is used to convert the Pydantic model to a dictionary and result is what we get after the validation is passes and now the workflow will get the result containing the false and empty list and checked ai response that is validated 
    }
@app.post("/validate")
def validate(request: TriageRequest):
    answer = triage(request.text)
    answer["id"] = request.id
    return answer 

