from fastapi import FastAPI
from data_types import MinerInput, MinerOutput

from ranking import rank_responses_by_quality_batch


abs_rubric_data = {
    "criteria": "Relevance, clarity, and detail in the response to the instruction.",
    "score1_description": "Poor response, lacking relevance or clarity.",
    "score2_description": "Mediocre response with partial relevance or clarity.",
    "score3_description": "Good response with reasonable relevance and clarity, but missing details.",
    "score4_description": "Very good response with strong relevance, clarity, and some detail.",
    "score5_description": "Excellent response with perfect relevance, clarity, and comprehensive detail."
}

rel_rubric = "Which response better aligns with relevance, clarity, and detail in answering the instruction?"


app = FastAPI()


@app.post("/solve")
async def solve(data: MinerInput):
    ranked_responses = rank_responses_by_quality_batch(
        data.prompt, data.responses, None, abs_rubric_data, rel_rubric
    )
    
    reponse_idx = {response: idx for idx, response in enumerate(data.responses)}
    final_rank = []
    for rank, score, response in ranked_responses:
        final_rank.append(reponse_idx[response])
    final_rank = [float(len(data.responses) -idx) / len(data.responses) for idx in final_rank]
    
    return MinerOutput(
        response_quality=final_rank
    )
    

@app.get("/health")
def health():
    return {"status": "ok"}
