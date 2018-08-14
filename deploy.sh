#!/usr/bin/env bash

# config
APP_HOST=206.81.1.131
REMOTE_DIR=/srv/live-bot
RSYNC_FLAGS="--exclude=.idea --exclude=env --exclude=.git --exclude=logs --exclude=__pycache__ -rPv"

# deploy
rsync ${RSYNC_FLAGS} . jawlecks@${APP_HOST}:${REMOTE_DIR}
ssh jawlecks@${APP_HOST} "docker build -f ${REMOTE_DIR}/dockerfile-livebot -t livebot ${REMOTE_DIR}"
#ssh jawlecks@${APP_HOST} "docker run livebot -d"