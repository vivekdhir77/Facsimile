import warnings
import sys
warnings.filterwarnings("ignore")  # Suppress warnings

from transformers import GPT2LMHeadModel, GPT2Tokenizer

def load_model(model_name="gpt2"):
    """Load GPT-2 model and tokenizer"""
    try:
        print("\nLoading GPT-2 model... (this may take a moment on first run)")
        tokenizer = GPT2Tokenizer.from_pretrained(model_name)
        model = GPT2LMHeadModel.from_pretrained(model_name)
        print("Model loaded successfully!")
        return model, tokenizer
    except Exception as e:
        print(f"Error loading model: {e}")
        sys.exit(1)

def generate_text(prompt, model, tokenizer, max_length=150, is_summary=False):
    """Generate text based on a prompt"""
    try:
        # If it's a summary request, modify the prompt
        if is_summary:
            prompt = f"Please summarize the following text:\n{prompt}\n\nSummary:"
        
        # Encode the input prompt
        input_ids = tokenizer.encode(prompt, return_tensors="pt")
        
        # Create attention mask
        attention_mask = input_ids.new_ones(input_ids.shape)
        
        # Generate text with different parameters for summaries
        outputs = model.generate(
            input_ids,
            attention_mask=attention_mask,
            max_length=max_length,
            num_return_sequences=1,
            no_repeat_ngram_size=2,
            do_sample=True,
            temperature=0.7 if not is_summary else 0.3,  # Lower temperature for summaries
            top_k=50,
            top_p=0.95,
            pad_token_id=tokenizer.eos_token_id
        )
        
        # Decode and return the generated text
        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return generated_text
    except Exception as e:
        return f"Error generating text: {e}"

def main():
    # Load model and tokenizer
    model, tokenizer = load_model()
    
    print("\nWelcome to GPT-2 Text Generator!")
    print("Type 'quit' or 'exit' to end the program")
    print("Type 'summarize' to enter summarization mode")
    print("-" * 50)
    
    try:
        while True:
            try:
                mode = input("\nDo you want to (g)enerate text or (s)ummarize? [g/s]: ").strip().lower()
                
                if mode in ['quit', 'exit']:
                    print("\nGoodbye!")
                    break
                
                is_summary = mode.startswith('s')
                
                prompt = input("\nEnter your " + ("text to summarize" if is_summary else "prompt") + ": ").strip()
                
                if prompt.lower() in ['quit', 'exit']:
                    print("\nGoodbye!")
                    break
                    
                if not prompt:
                    print("Please enter valid text!")
                    continue
                
                print(f"\nProcessing your " + ("summary" if is_summary else "text generation") + "...")
                print("-" * 50)
                generated_text = generate_text(prompt, model, tokenizer, is_summary=is_summary)
                print(f"\nGenerated " + ("summary" if is_summary else "text") + f":\n{generated_text}")
                print("-" * 50)
                
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
    
    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        print("\nPress Enter to exit...")
        input()

if __name__ == "__main__":
    main() 