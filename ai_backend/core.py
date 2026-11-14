from fastapi import FastAPI, UploadFile, File
from anthropic import Anthropic
from pydantic import BaseModel
from dotenv import load_dotenv
import os

app = FastAPI()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class TextLogInput(BaseModel):
    energy_score: int
    pain_score: int
    notes: str