import warnings
import sys
warnings.filterwarnings("ignore")  # Suppress warnings

from transformers import T5ForConditionalGeneration, T5Tokenizer

def load_model(model_name="t5-base"):
    """Load T5 model and tokenizer"""
    try:
        print("\nLoading T5 model... (this may take a moment on first run)")
        tokenizer = T5Tokenizer.from_pretrained(model_name)
        model = T5ForConditionalGeneration.from_pretrained(model_name)
        print("Model loaded successfully!")
        return model, tokenizer
    except Exception as e:
        print(f"Error loading model: {e}")
        sys.exit(1)

def generate_summary(text, model, tokenizer, max_length=150, min_length=40):
    """Generate summary of the input text"""
    try:
        # Prepare the text for T5
        text = "summarize: " + text
        
        # Encode the text
        input_ids = tokenizer.encode(text, return_tensors="pt", max_length=512, truncation=True)
        
        # Generate summary
        summary_ids = model.generate(
            input_ids,
            max_length=max_length,
            min_length=min_length,
            num_beams=4,
            no_repeat_ngram_size=2,
            early_stopping=True
        )
        
        # Decode and return the summary
        summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        return summary
    except Exception as e:
        return f"Error generating summary: {e}"

def main():
    # Load model and tokenizer
    model, tokenizer = load_model()
    
    print("\nWelcome to T5 Text Summarizer!")
    print("Type 'quit' or 'exit' to end the program")
    print("-" * 50)
    
    try:
        while True:
            try:
                # Get user input
                text = input("\nEnter the text to summarize (or 'quit' to exit): ").strip()
                
                if text.lower() in ['quit', 'exit']:
                    print("\nGoodbye!")
                    break
                    
                if not text:
                    print("Please enter some text to summarize!")
                    continue
                
                # Get desired summary length
                try:
                    max_words = input("\nMaximum summary length in words (press Enter for default): ").strip()
                    max_length = int(max_words) * 2 if max_words else 150
                except ValueError:
                    max_length = 150
                    print("Using default length...")
                
                print("\nGenerating summary...")
                print("-" * 50)
                summary = generate_summary(text, model, tokenizer, max_length=max_length)
                print(f"\nSummary:\n{summary}")
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