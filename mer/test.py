import argparse
import json
from collections import Counter

from mer.lm import LanguageModel
from mer.prompt import Prompt


def get_accuracy(test_json, prompt_config_path, output_json, api_key=None, num_samples=3, simple=False):

    with open(test_json, "r", encoding="utf-8") as f:
        testset = json.load(f)

    prompt = Prompt.from_file(prompt_config_path, simple=simple)
    lm = LanguageModel(api_key=api_key)

    total_num_sentences, total_penalty, total_correct, total_tokens = 0, 0, 0, 0
    results = []
    for i, example in enumerate(testset["examples"]):
        error_type, ref, rec, reason = prompt.unpack_example(example)
        # Add example information to item in json
        data = {"reference": ref, "recognised": rec}
        data["target"] = {"error": error_type, "reason": reason}

        # Create prompt and get continuations from lm
        prompt_string = prompt.create_prompt(ref, rec)
        continuations, response = lm.get_continuation(prompt_string, num_samples=num_samples)
        total_tokens += response["usage"]["total_tokens"]

        # Loop over text in continuatinos and extract results
        data["predicted"] = []
        errors = []
        for text in continuations:
            error_type_pred, reason_pred, _ = prompt.get_result(text)
            errors.append(error_type_pred)
            data["predicted"].append({"error": error_type_pred, "reason": reason_pred})

        # Run majority voting given the predicted error tpes
        counts = Counter(errors)
        final_prediction, count = counts.most_common()[0]

        outcome = "incorrect"
        if final_prediction == error_type:
            print(f"Got example {i} correct ({count}/{len(errors)})")
            outcome = "correct"
            total_correct += 1
        data["decided_error"] = final_prediction
        data["outcome"] = outcome
        results.append(data)

        # Keep track of score penalties to work out MER
        total_num_sentences += 1
        total_penalty += prompt.error2score[final_prediction]

    # Print total combined cost of running testset
    lm.print_cost("", tokens=total_tokens, num_samples=num_samples)  # actual cost

    # All serious errors makes this accuracy go to 0%, no errors and it is 100%
    meaning_accuracy = 100 * (total_num_sentences - total_penalty) / total_num_sentences
    meaning_error_rate = 100 - meaning_accuracy

    # Accuracy of LLM method to match human labels
    accuracy = 100 * total_correct / total_num_sentences

    # Store all information in output json
    output = {}
    output["results"] = results
    output["summary"] = {
        "total_tokens": total_tokens,
        "total_num_sentences": total_num_sentences,
        "total_penalty": total_penalty,
        "meaning_error_rate": round(meaning_error_rate, 2),
        "accuracy": round(accuracy, 2),
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    return accuracy, meaning_error_rate


def main():

    parser = argparse.ArgumentParser()
    # pylint: disable=line-too-long
    # fmt: off
    parser.add_argument("--test_json", type=str,default="./config/test.json", help="Json file containing examples with labels")  # noqa:  E201
    parser.add_argument("--prompt_config_path", type=str, default="./config/prompt.json", help="path to prompt config json")  # noqa:  E201
    parser.add_argument("--output_json", type=str, default="./results.json", help="path to output json to store results")  # noqa:  E201
    parser.add_argument("--api_key", type=str, default=None, help="api key for open ai")  # noqa:  E201
    parser.add_argument("--num_samples", type=str, default=3, help="number of times to sample GPT3 for majority voting")  # noqa:  E201
    # fmt: on
    args = parser.parse_args()

    accuracy, meaning_error_rate = get_accuracy(
        args.test_json, args.prompt_config_path, args.output_json, api_key=args.api_key, num_samples=args.num_samples
    )
    print(f"accuracy: {accuracy}, meaning_error_rate {meaning_error_rate}")


if __name__ == "__main__":
    main()
