FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[demo]"
# Hosts like Render and Hugging Face Spaces set PORT; OPENROUTER_API_KEY comes from the host's secrets.
ENV PORT=7860
EXPOSE 7860
CMD ["python", "-m", "jev_guard.demo"]
