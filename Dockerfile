FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 alpha && mkdir /data && chown alpha:alpha /data
COPY --chown=alpha:alpha server.py accounts.py index.html training.js charts.js nutrition.js nutrition-ui.js training-ui.js accounts-ui.js food_catalog.json ./
ENV PORT=3002 DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER alpha
EXPOSE 3002
CMD ["python", "server.py"]
