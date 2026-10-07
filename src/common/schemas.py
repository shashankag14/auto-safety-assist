from typing import Annotated

from pydantic import BaseModel, Field


class Candidates(BaseModel):
    """
    Defines the schema for a candidate returned by the retriever and passed as an input to the response generator.
    Each candidate should have the following fields listed below.

    (Refer the SQL database table definitions as a reference to declare the datatypes)
    """
    source: Annotated[str, Field(description="The source of the candidate")]
    id: Annotated[int, Field(description="The internal database ID of the candidate")]
    external_id: Annotated[str, Field(description="The NHTSA campaign number (recall) or ODI number "
                                       "(complaint) -- the ID citable to the end user")]
    vehicle_tag: Annotated[str, Field(description="The vehicle tag of the candidate")]
    text: Annotated[str, Field(description="The text of the candidate")]
    cosine_sim: Annotated[float, Field(description="The cosine similarity of the candidate", gt=0, le=1)]
