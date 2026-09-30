# Hugging Face Space (Docker SDK) for the FastAPI backend.
# The Space holds only this file and README.md; the code is pulled from GitHub at build time.
# Rebuild the Space (Settings -> Factory rebuild) to pick up new commits.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git libgomp1 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 MPLBACKEND=Agg
WORKDIR /home/user/app

ARG REPO=https://github.com/roshni2020/arian-os.git
ARG WILDFIREIA_COMMIT=aba9be9ef046a03e868a61c4139aa5bfcd7b5b56
# Busts the build cache whenever main moves, so a rebuild always gets the latest code.
ADD https://api.github.com/repos/roshni2020/arian-os/git/refs/heads/main /tmp/main-ref.json
RUN git clone --depth 1 $REPO . \
 && rm -rf WildfireIA frontend docs/demo \
 && git clone https://github.com/LabRAI/WildfireIA.git WildfireIA \
 && git -C WildfireIA checkout $WILDFIREIA_COMMIT
RUN pip install --no-cache-dir --user -r requirements.txt
# Pinned WildfireIA tables (~40 MB) and the metadata/all feature caches, baked into the image.
RUN python -m wildfire_researcher.cli setup-data

EXPOSE 7860
CMD ["uvicorn", "wildfire_researcher.api:app", "--host", "0.0.0.0", "--port", "7860"]
