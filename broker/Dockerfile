FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir anthropic==2.5.0
COPY main.py /app/main.py
USER nobody
CMD ["python", "/app/main.py"]
