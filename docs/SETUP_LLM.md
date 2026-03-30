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
python -m app.main

# Or explicitly specify the model:
LLM_MODEL=llama3.2 python -m app.main
```

That's it! The system will now use Ollama for much better responses.
