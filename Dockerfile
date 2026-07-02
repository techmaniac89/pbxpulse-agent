FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pbxpulse_agent ./pbxpulse_agent

RUN adduser --disabled-password --gecos "" pbxpulse \
  && mkdir -p /var/lib/pbxpulse-agent /var/log/pbxpulse-agent \
  && chown -R pbxpulse:pbxpulse /var/lib/pbxpulse-agent /var/log/pbxpulse-agent
USER pbxpulse

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3).read()"

CMD ["uvicorn", "pbxpulse_agent.main:app", "--host", "0.0.0.0", "--port", "8765"]
