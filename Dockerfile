FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY data/macro_events.csv ./data/macro_events.csv
COPY migrations ./migrations
COPY static ./static
RUN pip install --no-cache-dir .
EXPOSE 8765
CMD ["options-trader", "serve", "--host", "0.0.0.0", "--port", "8765"]

