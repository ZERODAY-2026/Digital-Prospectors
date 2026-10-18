import time
import ollama

def test_gemma():
    print("Testing connection to Ollama with model gemma3n:e2b...")
    start_time = time.time()
    response = ollama.generate(
        model="gemma3n:e2b",
        prompt="Respond with only the word 'OK'.",
        options={
            "temperature": 0,
            "num_predict": 10,
        },
        keep_alive="30m"
    )
    elapsed = time.time() - start_time
    text = response.get("response", "").strip()
    print(f"Response: '{text}'")
    print(f"Elapsed time: {elapsed:.2f} seconds")
    return elapsed

if __name__ == "__main__":
    test_gemma()
