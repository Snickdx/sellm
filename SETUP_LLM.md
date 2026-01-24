# LLM Setup Guide

This guide will help you set up a real LLM for much better, more natural responses.

## Quick Start with Ollama (Recommended)

### Step 1: Install Ollama

1. Go to [ollama.ai](https://ollama.ai)
2. Download and install Ollama for your operating system
3. Ollama will start automatically

### Step 2: Download a Model

Open a terminal and run:

```bash
# Recommended: llama3.2 (good balance of speed and quality)
ollama pull llama3.2

# Or try these alternatives:
# ollama pull mistral      # Alternative good option
# ollama pull phi3         # Smaller, faster
```

### Step 3: Verify Ollama is Running

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Or test with a simple query
ollama run llama3.2 "Hello"
```

### Step 4: Run Your App

```bash
# The app will auto-detect Ollama
python app.py

# Or explicitly specify the model:
LLM_MODEL=llama3.2 python app.py
```

That's it! The system will now use Ollama for much better responses.

## Why Use Ollama?

**Before (Template-based):**
- "Well, the system should be able to... integration accounting systems."
- Awkward grammar, limited variation

**After (Ollama + RAG):**
- "Oh, well the system needs to integrate with our accounting systems. That's really important for us because we need everything to sync up properly."
- Natural, grammatically correct, conversational

## Troubleshooting

### Ollama Not Detected

If you see "⚠ Ollama not available", check:

1. **Is Ollama running?**
   ```bash
   # Check if it's running
   curl http://localhost:11434/api/tags
   ```

2. **Start Ollama manually:**
   ```bash
   ollama serve
   ```

3. **Check firewall**: Make sure port 11434 is not blocked

### Model Not Found

If you get "model not found" errors:

```bash
# List available models
ollama list

# Pull the model again
ollama pull llama3.2
```

### Slow Responses

- Try a smaller model: `ollama pull phi3`
- Or use a faster model: `ollama pull mistral`
- Reduce context size in `llm_wrapper.py` (change `context_results[:3]` to `[:2]`)

## Using OpenAI Instead

If you prefer OpenAI (requires API key and costs money):

1. **Install package:**
   ```bash
   pip install openai
   ```

2. **Set API key:**
   ```bash
   export OPENAI_API_KEY="your-key-here"
   ```

3. **Run with OpenAI:**
   ```bash
   LLM_BACKEND=openai LLM_MODEL=gpt-3.5-turbo python app.py
   ```

## Comparison

| Feature | Template | Ollama | OpenAI |
|---------|----------|--------|--------|
| Quality | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Cost | Free | Free | Paid |
| Privacy | ✅ | ✅ | ❌ |
| Offline | ✅ | ✅ | ❌ |
| Setup | ✅ Easy | ✅ Easy | ⚠️ Needs API key |
| Speed | Fast | Medium | Fast |

**Recommendation**: Use Ollama with llama3.2 for the best balance of quality, cost, and privacy.
