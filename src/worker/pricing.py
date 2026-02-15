"""
Model pricing for cost estimation.
"""

# Per 1M tokens [input_price, output_price]
PRICING = {
    "deepseek-chat": [0.14, 0.28],
    "deepseek-reasoner": [0.55, 2.19],
    "gpt-4o": [2.50, 10.00],
    "gpt-4o-mini": [0.15, 0.60],
    "gpt-4.1": [2.00, 8.00],
    "gpt-4.1-mini": [0.40, 1.60],
    "gpt-4.1-nano": [0.10, 0.40],
    "o3-mini": [1.10, 4.40],
    "anthropic/claude-sonnet-4": [3.00, 15.00],
    "anthropic/claude-haiku-4.5": [0.80, 4.00],
    "google/gemini-2.5-flash-preview": [0.15, 0.60],
    "google/gemini-2.0-flash-001": [0.10, 0.40],
    "meta-llama/llama-4-maverick": [0.20, 0.60],
    "qwen/qwen3-235b-a22b": [0.20, 0.60],
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Estimate the cost of an API call.
    
    Args:
        model: Model name.
        input_tokens: Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.
    
    Returns:
        Estimated cost in USD.
    """
    prices = PRICING.get(model, [1.0, 3.0])  # Default fallback
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
