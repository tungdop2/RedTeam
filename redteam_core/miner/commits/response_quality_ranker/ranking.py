from typing import List, Tuple, Dict, Optional
from prometheus_eval.vllm import VLLM
from prometheus_eval import PrometheusEval
from prometheus_eval.prompts import ABSOLUTE_PROMPT, RELATIVE_PROMPT, SCORE_RUBRIC_TEMPLATE


# Initialize the model and evaluator
prometheus_model = VLLM(
    model="./prometheus-7b-v2.0.Q4_K_M.gguf",
    tokenizer="./models"
)

judge_model = PrometheusEval(
    model=prometheus_model,
    absolute_grade_template=ABSOLUTE_PROMPT, 
    relative_grade_template=RELATIVE_PROMPT
)


def calculate_absolute_grades(
    judge: PrometheusEval,
    instruction: str,
    responses: List[str],
    abs_score_rubric: str,
    reference_answer: Optional[str]
) -> Tuple[List[str], List[float]]:
    """Calculate absolute grades for all responses in batch."""
    instructions = [instruction] * len(responses)
    reference_answers = [reference_answer] * len(responses)
    return judge.absolute_grade(
        instructions=instructions,
        responses=responses,
        rubric=abs_score_rubric,
        reference_answers=reference_answers
    )

def group_responses_by_score(
    responses: List[str], 
    abs_scores: List[float]
) -> Dict[float, List[str]]:
    """Group responses by their absolute scores."""
    score_groups = {}
    for i, score in enumerate(abs_scores):
        if score not in score_groups:
            score_groups[score] = []
        score_groups[score].append(responses[i])
    return score_groups

def calculate_relative_rankings(
    judge: PrometheusEval,
    group: List[str],
    instruction: str,
    reference_answer: Optional[str],
    rel_rubric: str
) -> Dict[str, int]:
    """Calculate relative rankings within a score group."""
    relative_scores = {}
    for i, resp_a in enumerate(group):
        for j, resp_b in enumerate(group):
            if i >= j:
                continue
            data = {
                "instruction": instruction,
                "response_A": resp_a,
                "response_B": resp_b,
                "reference_answer": reference_answer,
                "rubric": rel_rubric
            }
            _, winner = judge.single_relative_grade(**data)
            winner_response = resp_a if winner == "A" else resp_b
            relative_scores[winner_response] = relative_scores.get(winner_response, 0) + 1
    return relative_scores

def rank_responses_by_quality_batch(
    instruction: str,
    responses: List[str],
    reference_answer: Optional[str],
    abs_rubric_data: Dict[str, str],
    rel_rubric: str,
) -> List[Tuple[int, float, str]]:
    """
    Ranks multiple responses to a given instruction based on absolute and relative grading.
    
    Args:
        instruction: The instruction or question being evaluated.
        responses: List of responses to be evaluated.
        reference_answer: Optional reference answer for grading.
        abs_rubric_data: Dictionary containing rubric details for absolute grading.
        rel_rubric: Single-sentence rubric for relative grading.
    
    Returns:
        List of tuples containing (rank, score, response).
    """
    # Prepare absolute grading rubric and calculate grades
    abs_score_rubric = SCORE_RUBRIC_TEMPLATE.format(**abs_rubric_data)
    _, abs_scores = calculate_absolute_grades(
        judge_model, instruction, responses, abs_score_rubric, reference_answer
    )

    # Group responses by score
    score_groups = group_responses_by_score(responses, abs_scores)

    # Rank responses within each score group
    final_rankings = []
    for score, group in sorted(score_groups.items(), key=lambda x: x[0], reverse=True):
        if len(group) > 1:
            relative_scores = calculate_relative_rankings(
                judge_model, group, instruction, reference_answer, rel_rubric
            )
            sorted_group = sorted(group, key=lambda x: relative_scores.get(x, 0), reverse=True)
            final_rankings.extend([(score, resp) for resp in sorted_group])
        else:
            final_rankings.append((score, group[0]))
    # Return ranked responses as (rank, score, response)
    return [(rank + 1, score, response) for rank, (score, response) in enumerate(final_rankings)]

if __name__ == "__main__":
    # Example Usage
    abs_rubric_data = {
        "criteria": "Relevance, clarity, and detail in the response to the instruction.",
        "score1_description": "Poor response, lacking relevance or clarity.",
        "score2_description": "Mediocre response with partial relevance or clarity.",
        "score3_description": "Good response with reasonable relevance and clarity, but missing details.",
        "score4_description": "Very good response with strong relevance, clarity, and some detail.",
        "score5_description": "Excellent response with perfect relevance, clarity, and comprehensive detail."
    }

    rel_rubric = "Which response better aligns with relevance, clarity, and detail in answering the instruction?"


    instruction = "What is a panda?"

    # reference_answer = (
    #     "The main causes of deforestation include agricultural expansion, logging, infrastructure development, and urbanization. "
    #     "These activities lead to habitat loss, a decline in biodiversity, and increased greenhouse gas emissions. "
    #     "Deforestation disrupts ecosystems, contributes to climate change, and affects water cycles, leading to soil erosion and desertification. "
    #     "Mitigation efforts such as reforestation, sustainable agriculture, and conservation policies are essential to address these issues."
    # )
    reference_answer = None

    responses = [
        "Hi",
        "The giant panda (Ailuropoda melanoleuca), sometimes called a panda bear or simply panda, is a bear species endemic to China.",
        "A panda is an animal.",
        "Pandas are black and white bears. They are known for eating bamboo.",
        "Pandas are a type of bear found in China. They are known for their distinctive black-and-white fur and love of bamboo."
    ]


    # Rank the responses
    ranked_responses = rank_responses_by_quality_batch(
        instruction, responses, reference_answer, abs_rubric_data, rel_rubric
    )

    # Print the rankings
    print("Ranked Responses:")
    for rank, score, response in ranked_responses:
        print(f"Rank: {rank}, Score: {score}, Response: {response}")
