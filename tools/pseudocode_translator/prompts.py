from .engineer import PromptEngineer


def extract_code(response: str) -> str:
    """Extract code from a model response"""
    engineer = PromptEngineer()
    return engineer.extract_code_from_response(response)
