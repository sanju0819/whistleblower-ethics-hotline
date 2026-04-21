import os

def generate_description(user_input):
    try:
        # Get path of prompt file
        base_dir = os.path.dirname(os.path.dirname(__file__))
        prompt_path = os.path.join(base_dir, "prompts", "describe_prompt.txt")

        # Read prompt
        with open(prompt_path, "r") as file:
            prompt_template = file.read()

        # Replace input
        final_prompt = prompt_template.replace("{user_input}", user_input)

        # Mock response (Day 2)
        response = f"This complaint describes a potential ethical issue: {user_input}"

        return response

    except Exception as e:
        return str(e)