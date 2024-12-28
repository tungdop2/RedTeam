from typing import List, Union
from transformers import AutoTokenizer, AutoModelForCausalLM


class VLLM:
    def __init__(
        self,
        model_id: str,
        filename: str,
    ) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, gguf_file=filename)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, gguf_file=filename)

    def validate_vllm(self):
        return True

    def completions(
        self,
        prompts: List[str],
        use_tqdm: bool = True,
        **kwargs: Union[int, float, str],
    ) -> List[str]:
        prompts = [prompt.strip() for prompt in prompts]
        
        outputs = []
        for prompt in prompts:
            inputs = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
            generated_ids = self.model.generate(
                **inputs,
                **kwargs,
            )
            outputs.append(self.tokenizer.decode(generated_ids[0][inputs['input_ids'].size(1):], skip_special_tokens=True))
        
        return outputs


if __name__ == "__main__":
    vllm = VLLM(
        "./models",
        "prometheus-7b-v2.0.Q4_K_M.gguf",
    )
    print(vllm.completions(["Hello, how are you?"]))
