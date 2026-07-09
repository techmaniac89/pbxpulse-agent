FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pbxsense_agent ./pbxsense_agent

RUN adduser --disabled-password --gecos "" pbxsense \
  && mkdir -p /var/lib/pbxsense-agent /var/log/pbxsense-agent \
  && chown -R pbxsense:pbxsense /var/lib/pbxsense-agent /var/log/pbxsense-agent
USER pbxsense

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3).read()"

CMD ["uvicorn", "pbxsense_agent.main:app", "--host", "0.0.0.0", "--port", "8765"]
