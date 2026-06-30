#!/bin/bash
# Start the Ollama server (module binary) using the shared Oak model cache. OpenAI-compatible API on :11434.
OB=/share/software/user/open/ollama/0.30.5
export PATH=$OB/bin:$PATH
# gcc-14 libstdc++ FIRST (el7's /usr/lib64 is too old: missing GLIBCXX_3.4.26 / CXXABI_1.3.13)
export LD_LIBRARY_PATH=/share/software/user/open/gcc/14.2.0/lib64:$OB/lib/ollama:$OB/lib:/share/software/user/open/cuda/12.6.1/lib64:${LD_LIBRARY_PATH:-}
export OLLAMA_MODELS=$SCRATCH/.ollama/models
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_KEEP_ALIVE=30m
H=/scratch/users/karun09/Version_2/h100_session
setsid "$OB/bin/ollama" serve > "$H/ollama.log" 2>&1 &
echo "ollama serve pid=$!"
