import math
from typing import Literal, Optional

from pydantic import BaseModel

TARGET_TYPE = Literal["experiment", "run"]

class Annotation(BaseModel):
    id: str
    target_type: TARGET_TYPE
    target_id: str
    text: str
    tags: list[str]
    author: str
    created_at: str
    updated_at: str
    version: int

class AnnotationInput(BaseModel):
    target_type: TARGET_TYPE
    target_id: str
    text: str
    tags: list[str]
    author: str

class AnnotationUpdate(BaseModel):
    text: str
    tags: list[str]
    version: Optional[int] = None


def to_annotation(record):
    return Annotation(**{field: record[field] for field in Annotation.model_fields})
