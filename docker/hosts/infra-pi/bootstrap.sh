#!/bin/bash

echo -e " \033[33;5m  _        __         ___  _   \033[0m"
echo -e " \033[33;5m (_)_ _  / _|_ _ __ _| _ \(_)  \033[0m"
echo -e " \033[33;5m | | ' \|  _| '_/ _\` |  _/ |   \033[0m"
echo -e " \033[33;5m |_|_||_|_| |_| \__,_|_| |_|   \033[0m"
echo -e " \033[36;5m   Bootstrap :: infra-pi         \033[0m"
echo -e " \033[36;5m   https://github.com/gregpakes/homelab \033[0m"
echo -e ""

#############################################
# YOU SHOULD ONLY NEED TO EDIT THIS SECTION #
#############################################

REPO_URL="https://github.com/gregpakes/homelab.git"
REPO_DIR="/opt/homelab"
CURRENT_USER=$(id -un)

#############################################
#            DO NOT EDIT BELOW              #
#############################################

# Install Docker if not already present
if ! command -v docker &>/dev/null; then
  echo -e " \033[31;5mDocker not found, installing...\033[0m"
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$CURRENT_USER"
  echo -e " \033[32;5mDocker installed.\033[0m"
else
  echo -e " \033[32;5mDocker already installed.\033[0m"
fi

# Work out whether we need sudo for docker
# (group membership not active until next login after fresh install)
if docker info &>/dev/null 2>&1; then
  DOCKER="docker"
else
  echo -e " \033[33;5mDocker group not yet active for $CURRENT_USER, using sudo for docker commands.\033[0m"
  DOCKER="sudo docker"
fi

# Clone or update the homelab repo
if [ ! -d "$REPO_DIR/.git" ]; then
  echo -e " \033[31;5mRepo not found, cloning to $REPO_DIR...\033[0m"
  sudo mkdir -p "$REPO_DIR"
  sudo chown "$CURRENT_USER":"$CURRENT_USER" "$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
  echo -e " \033[32;5mRepo cloned.\033[0m"
else
  echo -e " \033[32;5mRepo already present, pulling latest...\033[0m"
  git -C "$REPO_DIR" pull --ff-only
fi

# Start portainer-agent
echo -e " \033[33;5mStarting portainer-agent...\033[0m"
$DOCKER compose -f "$REPO_DIR/docker/hosts/infra-pi/portainer-agent/docker-compose.yml" up -d
echo -e " \033[32;5mPortainer agent is up on port 9001.\033[0m"

echo -e ""
echo -e " \033[32;5mBootstrap complete\033[0m"
echo -e " \033[36;5mNext: add this Pi as an Agent environment in Portainer.\033[0m"
echo -e " \033[36;5m  Environment type : Agent\033[0m"
echo -e " \033[36;5m  URL              : $(hostname -I | awk '{print $1}'):9001\033[0m"
echo -e ""
